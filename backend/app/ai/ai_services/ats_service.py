import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Literal

import openai
from langsmith import traceable
from pydantic import BaseModel, Field, ValidationError
from app.core.config import get_llm, settings
from app.database import db_cursor

logger = logging.getLogger(__name__)


class ATSValidationError(Exception):
    """Raised when the LLM's ATS output fails strict validation against `_ATSLLMOutput`.

    Distinct from transient/network errors (see `_invoke_ats_llm`'s retry) — a malformed
    response is not retryable, and callers must treat it as a hard stop: never persist it.
    """

# Legacy default — used only when a job posting predates recruiter-defined ats_criteria
# (JobPostings.ats_criteria IS NULL).
_CATEGORY_WEIGHTS: dict[str, float] = {
    "experience": 30,
    "skills": 35,
    "projects": 20,
    "certifications": 5,
    "education": 5,
    "achievements": 5,
}

_CATEGORY_LABELS: dict[str, str] = {
    "experience": "Professional Experience",
    "skills": "Technical & Soft Skills",
    "projects": "Projects",
    "certifications": "Certifications",
    "education": "Education",
    "achievements": "Achievements & Quantifiable Results",
}

# Fixed per-row max on the 0/0.5/1 requirement scale (see STEP 5 in _SYSTEM_PROMPT). match_type
# classification is resolved by the LLM; the score itself is looked up deterministically here
# rather than trusted from the model's own arithmetic. "exceeds" no longer scores above the 1.0
# cap — it's the same full credit as "exact", just flagged via exceeds_requirement so a reviewer
# can see the candidate over-delivers on that specific requirement without inflating the section %.
_MATCH_TYPE_SCORES: dict[str, float] = {
    "exact": 1.0,
    "parent": 1.0,
    "exceeds": 1.0,
    "alternative": 0.5,
    "not_found": 0.0,
    "not_required": 0.0,
}
_REQUIREMENT_MAX_SCORE = 1.0


@dataclass
class ParsedATSCriteria:
    """Normalized shape of JobPostings.ats_criteria, regardless of which of the three
    on-disk shapes it's in (NULL, legacy bare array, or the current criteria+thresholds
    object). Shared by ATS scoring (check_ats_eligibility) and any read-only UI that
    needs to display a job's configured ATS criteria (e.g. the recruiter dashboard).
    """

    has_config: bool
    criteria: list[dict] = field(default_factory=list)
    qualify_threshold: float = 65.0
    overqualify_threshold: float | None = None
    auto_reject_overqualified: bool = False


def parse_ats_criteria(ats_criteria_json: str | None) -> ParsedATSCriteria:
    parsed: object = None
    if ats_criteria_json:
        try:
            parsed = json.loads(ats_criteria_json)
        except (json.JSONDecodeError, TypeError):
            parsed = None

    if isinstance(parsed, list):
        # Legacy shape: bare criteria array, no threshold config yet.
        return ParsedATSCriteria(has_config=True, criteria=parsed)
    if isinstance(parsed, dict):
        return ParsedATSCriteria(
            has_config=True,
            criteria=parsed.get("criteria", []),
            qualify_threshold=(
                parsed.get("qualify_threshold") if parsed.get("qualify_threshold") is not None else 65.0
            ),
            overqualify_threshold=parsed.get("overqualify_threshold"),
            auto_reject_overqualified=bool(parsed.get("auto_reject_overqualified", False)),
        )
    # NULL or malformed — job predates recruiter-defined ATS weighting, or the JSON
    # didn't parse; fall back to defaults exactly as if no config were set at all.
    return ParsedATSCriteria(has_config=False)


# ============================================================
# Raw LLM output schema — the model extracts and classifies evidence;
# all numeric scores are then derived deterministically in Python
# rather than trusted from the model's own arithmetic.
# ============================================================


# The 5 ats_criteria sections that requirement_matching rows can be tagged with. "experience" is
# deliberately excluded — years/seniority/responsibility-fit requirements are handled by the
# separate relevant_experience.responsibility_matches below, not mixed into this flat list, so
# there is exactly one place that owns each kind of requirement.
_REQUIREMENT_CATEGORIES = ("skills", "projects", "certifications", "education", "achievements")


class _RequirementMatchLLM(BaseModel):
    requirement: str
    category: Literal["skills", "projects", "certifications", "education", "achievements"]
    candidate_evidence: str | None = None
    match_type: Literal["exact", "parent", "alternative", "exceeds", "not_found", "not_required"]
    confidence: Literal["high", "medium", "low"]
    reason: str


class _ResponsibilityMatchLLM(BaseModel):
    requirement: str
    evidence: str | None = None
    match_type: Literal["direct", "close", "not_found"]


class _RelevantExperienceLLM(BaseModel):
    job_role_required: str
    included_experience: str
    excluded_experience: str | None = None
    required_years: float | None = None
    candidate_relevant_years: float | None = None
    status: Literal["qualified", "underqualified", "overqualified"]
    responsibility_matches: list[_ResponsibilityMatchLLM] = Field(default_factory=list)


class _SectionMatchLLM(BaseModel):
    section: Literal["projects", "certifications", "education", "achievements"]
    jd_requires_section: bool
    cv_has_content: bool
    score: float = Field(ge=0, le=100)
    note: str


class _GraceCreditLLM(BaseModel):
    item: str
    points: float
    note: str


class _ATSLLMOutput(BaseModel):
    """Raw structured output requested from the LLM — extraction + classification only.

    Category weightage and the weighted_average are computed deterministically in Python from
    this data (see `_score_ats_output`) rather than trusted from the model's own arithmetic.
    """

    verdict: Literal["QUALIFIED", "UNDERQUALIFIED", "OVERQUALIFIED"]
    verdict_summary: str = Field(
        description="3-5 sentence NEUTRAL, adjective-free summary: strongest section, weakest "
        "section, and one concrete gap a human reviewer should double-check. Must not assert or "
        "imply a qualified/underqualified/overqualified judgment of its own — the `verdict` field "
        "is the sole place that judgment is stated, and this text must never contradict it."
    )
    requirement_matching: list[_RequirementMatchLLM] = Field(default_factory=list)
    relevant_experience: _RelevantExperienceLLM
    section_matching: list[_SectionMatchLLM] = Field(default_factory=list)
    grace_credits: list[_GraceCreditLLM] = Field(default_factory=list)
    additional_cv_content: list[str] = Field(default_factory=list)


# ============================================================
# Final response schema (deterministically computed, persisted, and returned to the API/frontend)
# ============================================================


class ATSCategoryScore(BaseModel):
    score_pct: float
    weight_pct: float
    weighted_score: float
    # True if the recruiter's ats_criteria explicitly selected this section (or it's a legacy job
    # using the _CATEGORY_WEIGHTS default, where every section counts). False means the recruiter
    # excluded it — distinct from a section that was selected but legitimately scored 0.
    included: bool
    matched_count: int | None = None
    total_count: int | None = None


class ATSWeightage(BaseModel):
    experience: ATSCategoryScore
    skills: ATSCategoryScore
    projects: ATSCategoryScore
    certifications: ATSCategoryScore
    education: ATSCategoryScore
    achievements: ATSCategoryScore
    weighted_average: float
    qualify_threshold: float
    pass_fail: Literal["PASS", "FAIL"]


class RequirementMatchResult(BaseModel):
    requirement: str
    category: Literal["skills", "projects", "certifications", "education", "achievements"]
    candidate_evidence: str | None = None
    match_type: Literal["exact", "parent", "alternative", "exceeds", "not_found", "not_required"]
    exceeds_requirement: bool = False
    score: float
    max_score: float = _REQUIREMENT_MAX_SCORE
    confidence: Literal["high", "medium", "low"]
    reason: str


class ResponsibilityMatchResult(BaseModel):
    requirement: str
    evidence: str | None = None
    match_type: Literal["direct", "close", "not_found"]
    score: float


class RelevantExperienceResult(BaseModel):
    job_role_required: str
    included_experience: str
    excluded_experience: str | None = None
    required_years: float | None = None
    candidate_relevant_years: float | None = None
    status: Literal["qualified", "underqualified", "overqualified"]
    responsibility_matches: list[ResponsibilityMatchResult] = Field(default_factory=list)


class SectionMatchResult(BaseModel):
    section: str
    jd_requires_section: bool
    cv_has_content: bool
    score: float
    note: str


class GraceCredit(BaseModel):
    item: str
    points: float
    note: str


class ATSCheckResult(BaseModel):
    verdict: Literal["QUALIFIED", "UNDERQUALIFIED", "OVERQUALIFIED"]
    verdict_summary: str
    weightage: ATSWeightage
    requirement_matching: list[RequirementMatchResult] = Field(default_factory=list)
    relevant_experience: RelevantExperienceResult
    section_matching: list[SectionMatchResult] = Field(default_factory=list)
    grace_credits: list[GraceCredit] = Field(default_factory=list)
    additional_cv_content: list[str] = Field(default_factory=list)
    # Axis 2 (Part A) — independent of the PASS/FAIL verdict above.
    is_overqualified: bool = False
    final_verdict: Literal["PASS", "FAIL"]
    override_reason: str | None = None


_SYSTEM_PROMPT = """
=========================================
ATS SCORING ENGINE — ROLE-RELEVANCE MODEL
=========================================

You are an ATS Scoring Engine. You extract, match, and score a candidate's CV against a job
posting's requirements, using role-relevant evidence only. You never guess. Every score must
trace back to explicit text in the JD and explicit text in the CV.

=========
INPUTS
=========
Current Date: {current_date}
Job Posting: {job_post_data}
Candidate CV: {candidate_cv_data}
Scoring Weights: {ats_criteria}

=========
DEFINITIONS (apply these exactly, do not reinterpret)
=========
- EXPLICIT: stated in words in the JD or CV. Not implied, not assumed, not inferred from tone.
- PARENT SKILL: a foundational skill that a listed skill technically requires (e.g. PyTorch
  requires Python). Credit the parent ONLY when the JD asks for the parent and the CV lists the
  child skill explicitly — never the reverse.
- ALTERNATIVE / SIBLING SKILL: a different tool serving the same function at the same level
  (e.g. TensorFlow vs PyTorch, MySQL vs PostgreSQL). Not a synonym, not a parent/child pair.
- RELEVANT EXPERIENCE: only the portion of the candidate's work history whose role/responsibilities
  match the job posting's role. Time in unrelated roles is EXCLUDED from years-of-experience
  totals, even if the candidate held that job longer.
- QUALIFIED / UNDERQUALIFIED / OVERQUALIFIED: a judgment on relevant experience vs the JD's
  stated requirement — not a JD requirement vs total candidate history.

=========
STEP 1 — JOB REQUIREMENT EXTRACTION
=========
1.1 Identify the job role first (title + core function). Every downstream extraction is filtered
    through this role — do not extract requirements generic to "any job" unless the JD states them.

1.1.1 JD-ONLY RULE: the requirement list you build in this step comes from the Job Posting text
    ONLY — do not look at, or let the Candidate CV influence, which requirements you list or how
    many there are. The same JD must always yield the same fixed set of requirement rows,
    regardless of which candidate's CV you are scoring. Only the per-row match_type (Step 5) may
    vary between candidates — the requirement rows themselves never do.

1.2 List every requirement under two buckets:
    - PRIMARY: stated as required, mandatory, core to daily responsibilities.
    - SECONDARY: stated as helpful, preferred, or supporting context.
    Use the JD's own language to decide the bucket — "must have" / "required" = PRIMARY,
    "preferred" / "familiarity with" / "a plus" = SECONDARY. If the JD gives no signal, default
    to PRIMARY for anything tied to the role's core function, SECONDARY otherwise.

1.3 ATOMIC SPLIT RULE: never bundle. Any comma/slash/"and"/"or"-separated list of skills, tools,
    or competencies becomes one row per item, each keeping the tier of the sentence it came from.
    Example: "English communication A1/C1, and proficiency in Salesforce" → two rows:
    "English communication (A1/C1)" [own tier], "Salesforce" [own tier].

1.4 Do not create a requirement row for a job title, a role-equivalence statement, a general
    years-of-experience/seniority line, or a specific responsibility statement (e.g. "must have
    led cross-functional teams") — these all go to relevant_experience instead (job-title/years/
    seniority into relevant_experience's own fields, specific responsibility statements into
    relevant_experience.responsibility_matches). Do not duplicate them here.

1.5 CATEGORY TAGGING: every requirement row you DO create here must be tagged with exactly one
    category — "skills" (a named tool/technology/technique/competency), "projects" (an explicit
    ask to demonstrate project work, e.g. "must show a portfolio"), "certifications" (a named or
    implied certification/license), "education" (a degree/qualification-level requirement), or
    "achievements" (a measurable-outcome requirement, e.g. "track record of hitting sales
    targets"). This tag determines which section score the row contributes to — get it right,
    don't default everything to "skills".

1.6 PRE-EXTRACTION CHECK (silent, internal — do not print): before moving to Step 2, list every
    requirement you found in one pass. Re-read the JD once more specifically hunting for anything
    you missed — soft skills, language requirements, tool names buried mid-sentence. Requirements
    are frequently under-counted on the first pass; the second pass is mandatory.

1.7 DEDUP CHECK: if the JD states the same requirement more than once in different words (e.g.
    once in a "Requirements" bullet list and again, reworded, in the role summary or
    responsibilities prose), collapse it into a single requirement row — never create two rows for
    what is really one underlying ask. Keep the clearer/more specific wording of the two.

=========
STEP 2 — CV EXTRACTION
=========
2.1 Extract skills and experience from ALL core sections — Skills, Experience, Projects,
    Certifications, Education, Achievements. Unlike a skills-only scan, evidence from a project
    description or a work-experience bullet DOES count here — use it.

2.2 RELEVANCE FILTER: only keep CV content whose role/domain matches the job posting's role.
    If the candidate held multiple roles (e.g. 5 years as Software Engineer, then 3 years as
    Manager) and the JD is for a Manager role, extract and count ONLY the 3 years and its
    associated skills/responsibilities. State explicitly which experience was excluded and why.

2.2.1 DATE MATH: use the Current Date given in INPUTS above to resolve "Present"/"Current"/
    "Till date" end dates — never guess or assume an end date. When the candidate held multiple
    SEQUENTIAL, NON-OVERLAPPING relevant roles (e.g. two back-to-back Software Engineer roles at
    different companies), SUM the duration of every relevant role together — do not truncate to
    only the most recent one. Only exclude a role's time if it fails the relevance filter above or
    genuinely overlaps another counted role (in which case count the overlap once).

2.3 PARENT SKILL CREDIT: if the JD requires a parent skill (e.g. "Python") and the CV explicitly
    lists a child/derivative tool (e.g. "PyTorch"), credit the parent skill as matched. Note the
    inference in the reasoning field. Do not do this in reverse (child requirement + parent-only
    CV listing does NOT auto-credit the child). This credit does NOT require the CV to literally
    spell out the parent-child relationship — the relationship itself is domain knowledge you are
    expected to apply. Worked examples:
    - JD requires "Python"; CV lists "PyTorch", "Django", or "pandas" (all Python-only libraries)
      → match_type "parent", full credit. Reason cites the CV's specific tool and states it is a
      Python library.
    - JD requires "SQL"; CV lists "PostgreSQL" or "MySQL" (SQL-based RDBMSs) → match_type "parent".
    - JD requires "cloud infrastructure"; CV explicitly lists "AWS EC2/S3" → match_type "parent".

2.4 ALTERNATIVE SKILL CREDIT: if the JD requires a tool and the CV lists a different tool serving
    the same function at the same level, record it as an alternative match (see Step 5 scoring).
    Also applies when the CV shows a skill at a level that exceeds what was asked (e.g. JD asks
    for "basic SQL" and the CV shows advanced/production SQL usage) — that is match_type
    "exceeds", not "not_found"; never miss credit just because the CV evidence is stronger than
    the literal ask. Worked examples:
    - JD requires "MySQL"; CV lists "PostgreSQL" (different RDBMS, same function/level) → match_type
      "alternative", half credit.
    - JD requires "basic SQL query writing"; CV shows evidence of complex joins, query
      optimization, or stored procedures → match_type "exceeds", full credit, note the deeper
      evidence in reason.
    - JD requires "project management"; CV shows explicit Agile/Scrum sprint-ownership experience
      → match_type "exceeds" or "parent" depending on framing, never "not_found".

2.5 Certifications only count if industry-recognized (issued by a known vendor, accrediting body,
    or standards body). Generic, self-issued, or unverifiable certifications score 0 regardless of
    stated relevance. A license or credential issued by a government body, statutory regulator, or
    bar/professional council (e.g. a Bar Council license to practice law, a medical board license,
    a CPA license from a state board) is ALWAYS industry-recognized by definition — never score
    these 0 for "not being industry-recognized." Evaluate each such credential on its own merits
    (does it match what the JD requires, is it stated as active) rather than questioning the
    issuing body's legitimacy. This "industry-recognized" verification bar applies to
    CERTIFICATIONS ONLY —
    do NOT apply it to standard academic Education. A named degree/diploma from any institution
    the CV states counts as valid education by default; do not penalize it as "unverifiable" for
    lacking third-party accreditation proof, and do not penalize an in-progress or incomplete
    degree beyond what the JD itself asks for (see Step 4 for exactly how Education is scored
    against the JD's literal wording).

=========
STEP 3 — AMBIGUITY TIE-BREAKERS
=========
- If a skill appears both explicitly required in the requirements list AND embedded in the job
  title (e.g. "Salesforce Administrator" + "must know Salesforce") — treat as one PRIMARY
  requirement, do not double-count.
- If a CV skill could be read as either a parent-skill match or an alternative match, PARENT
  match takes precedence when the derivative relationship is exact; ALTERNATIVE only applies
  when there is no parent/child relationship.
- If relevant-experience duration is ambiguous (overlapping roles, unclear dates), state the
  ambiguity in the note and use the more conservative (lower) year count.

=========
STEP 4 — SECTION-LEVEL MATCHING
=========
For each of Projects, Certifications, Education, Achievements, produce ONE section_matching entry
(score 0-100) that answers a single question: "does the CV satisfy what the JD LITERALLY asked
for in this section?" — not "how impressive is this candidate's background in general." Score
against the JD's own stated bar, never an absolute/external standard the JD didn't set.

- JD implies the section (states or clearly implies a requirement in it), CV has matching content
  → score based on how fully the CV's content meets the JD's literal ask (100 = fully meets it).
- JD implies the section, CV has none → score 0.
- JD does NOT require the section at all → score 0, note "not required by JD"; if the CV has
  content here anyway that's clearly role-relevant, add a grace credit (1-2 points, see below)
  instead of inflating this section's score.

EDUCATION — the most common scoring error is treating this as "how prestigious/complete is the
degree" instead of "does it satisfy what the JD literally asked for." Read the JD's exact
education line before scoring:
- JD says something permissive ("fresh graduates welcome", "no degree required", "in-progress
  accepted", or states no education requirement at all) → ANY relevant degree (including
  in-progress/incomplete) or even no degree satisfies this. Score at or near 100. Do not deduct
  points for the degree being unfinished, from an unverified institution, or unrelated in minor
  ways — the JD explicitly set a low bar, honor it.
- JD requires a specific completed degree/level (e.g. "Bachelor's in Computer Science required")
  → score against exactly that: completed + matching field = 100; in-progress or a related-but-
  different field = partial credit (40-70, state why); no relevant education = 0.
Certifications and Achievements follow the same principle: score against the JD's literal ask,
not a generic quality bar. (Certifications still separately require industry recognition per
Step 2.5 to count as a match at all — that's about whether a claimed credential counts, not about
inflating/deflating the section score once it does.)

Grace credit: CV has role-relevant content in a section the JD didn't ask for → 1-2 points, added
as a note only, never blended into the weighted average as part of that section's score. This is
REQUIRED, not optional: if the CV contains ANY substantive, role-relevant item that the JD never
asked for (a certification, a notable achievement, a project, an extra qualification), you MUST
add a grace_credits entry for it — do not leave grace_credits empty when such content exists in
the CV. Only leave it empty when the CV genuinely has no unrequired-but-relevant content.

=========
STEP 5 — REQUIREMENT-LEVEL SCORING (0 / 0.5 / 1 scale)
=========
For every individual requirement row from Step 1, classify the match_type against CV evidence
from Step 2 — you report match_type only, the numeric score is derived from it downstream:

| JD requires | Candidate has | match_type | Rule |
|---|---|---|---|
| A | A | exact | Exact match — full credit |
| A | A, at clearly greater depth/seniority | exceeds | Candidate exceeds requirement — must show real evidence of deeper expertise, not just extra words. Still full credit (not extra) — this is a flag for reviewers, not a bonus multiplier |
| A | A via a parent skill per Step 2.3 | parent | Full credit |
| A | B (alternative/sibling) | alternative | Half credit per Step 2.4 |
| A | — (not found) | not_found | No evidence anywhere in relevant CV sections — zero credit |
| — (not required) | A | not_required | Present but irrelevant to any stated requirement — zero credit, does not add or subtract |

Every row requires:
- Its category tag (Step 1.5).
- A 1–2 sentence reason citing the specific JD text and specific CV text used.
- A confidence flag: HIGH / MEDIUM / LOW. Use MEDIUM/LOW whenever the match relies on an
  inference (parent-skill credit, alternative credit, relevance filtering judgment calls) so a
  human reviewer knows where to double-check.

RESPONSIBILITY MATCHING (relevant_experience.responsibility_matches): for each specific
responsibility statement excluded from requirement_matching per Step 1.4, classify match_type as
"direct" (CV shows this exact responsibility performed), "close" (CV shows closely related but
not identical work), or "not_found" (no evidence). Same reason/evidence requirement as above.

=========
STEP 6 — SECTION SCORING
=========
- section_matching scores (Step 4) and requirement_matching rows (Step 5) are the only inputs
  this step produces — do NOT compute or output a weighted average yourself; that is done
  downstream from your requirement- and section-level output using the weights in {ats_criteria}.
- A section with no scorable data still counts at its full assigned weight, scoring 0% for that
  section. Never redistribute a missing section's weight onto other sections.
- Grace-credit points from Step 4 are reported separately and do NOT get folded into the
  weighted average — they are reviewer context only.
- FYI (for your own reasoning, not something you compute): the Experience category score shown
  to reviewers is derived downstream as 30% years/seniority fit + 70% itemized
  responsibility_matches coverage — this is why an experience score won't equal the raw
  responsibility-match ratio alone. You don't need to output this number; it's computed in code
  from your relevant_experience.status/years and responsibility_matches fields.

=========
STEP 7 — VERDICT
=========
Do not output a binary PASS/FAIL. Instead classify relevant-experience-and-skills fit as:
- QUALIFIED — relevant experience and requirement coverage meet the JD's stated level.
- UNDERQUALIFIED — relevant experience/skills fall short of the JD's stated level. State the gap
  in concrete terms (e.g. "JD requires 5 yrs relevant experience; candidate has 3").
- OVERQUALIFIED — relevant experience substantially exceeds the JD's stated level (e.g. senior/
  staff-level candidate against a junior posting). This is a mismatch, not a bonus — flag it as
  such, do not treat it as automatically positive.
Base this ONLY on relevant experience (per Step 2.2's filter) vs the JD's stated requirement —
never on total career history. The `verdict` field is the ONLY place this judgment is stated.
verdict_summary itself must stay neutral and descriptive — 3-5 sentences covering strongest
section, weakest section, and one concrete gap a human reviewer should verify — with no
qualified/underqualified/overqualified language of its own, and it must never contradict the
`verdict` field. (A separate numeric PASS/FAIL against the recruiter's own threshold is computed
downstream from your section scores — not your concern here; this verdict is purely your
experience-based judgment call.)

=========
SELF-VERIFICATION (silent, internal — do not print, do not skip)
=========
Before producing final output, check:
1. Does every JD requirement from Step 1 have a corresponding row in the output?
2. Was any CV evidence used that falls outside the relevance filter (Step 2.2)? Remove it if so.
3. Does every requirement_matching row have a category, a reason, and a confidence flag?
4. Is the verdict based on relevant experience only, not total years?
5. Did Education get scored against the JD's literal wording (Step 4), not a generic prestige or
   accreditation bar?
6. For every row currently marked "not_found": could a parent skill (2.3), an alternative/sibling
   skill (2.4), or a deeper/exceeding form of the requirement actually apply given the CV's
   evidence? If yes, reclassify it — do not leave credit on the table.
7. Does verdict_summary contain any verdict-judgment words ("qualified", "underqualified",
   "strong fit", "not a fit", etc.) or any claim that isn't consistent with the actual verdict/
   status/score fields elsewhere in this output? If so, rewrite it to be purely descriptive
   (strongest section, weakest section, one concrete gap) with no adjective-laden verdict of its
   own — the verdict field is the only place the verdict is stated.
8. If candidate_relevant_years is less than the sum of durations of every role you found that
   matches the JD's role/domain, does excluded_experience explicitly state which role(s)/time
   span were cut and why? An empty or null excluded_experience is only valid when nothing was
   excluded.

=========
OUTPUT FORMAT — JSON ONLY, no prose outside it
=========
{
  "verdict": "QUALIFIED" | "UNDERQUALIFIED" | "OVERQUALIFIED",
  "verdict_summary": "3-5 sentence string, specific to this candidate and this JD",
  "requirement_matching": [
    {
      "requirement": "string",
      "category": "skills" | "projects" | "certifications" | "education" | "achievements",
      "candidate_evidence": "string or null",
      "match_type": "exact" | "parent" | "alternative" | "exceeds" | "not_found" | "not_required",
      "confidence": "high" | "medium" | "low",
      "reason": "string — cites specific JD text and specific CV text"
    }
  ],
  "relevant_experience": {
    "job_role_required": "string",
    "included_experience": "string — what was counted and why",
    "excluded_experience": "string or null — MUST be populated (not null) whenever any in-domain role's time was cut from candidate_relevant_years; state exactly which role(s)/span were cut and why. Only null when nothing relevant was excluded",
    "required_years": number,
    "candidate_relevant_years": number,
    "status": "qualified" | "underqualified" | "overqualified",
    "responsibility_matches": [
      {"requirement": "string", "evidence": "string or null", "match_type": "direct" | "close" | "not_found"}
    ]
  },
  "section_matching": [
    {"section": "string", "jd_requires_section": boolean, "cv_has_content": boolean, "score": number, "note": "string"}
  ],
  "grace_credits": [
    {"item": "string", "points": number, "note": "string"}
  ],
  "additional_cv_content": ["string — present in CV but tied to no requirement"]
}

=========
GUARDRAILS
=========
- Never award a score without a specific reason citing exact JD and CV text.
- Never count time from a role irrelevant to the job posting toward years-of-experience.
- Never credit a parent skill in reverse (child requirement satisfied by parent-only CV listing).
- Never bundle multiple distinct requirements into one row — split every list, every sentence.
- Never treat overqualification as automatically positive — it is a mismatch, flag it as one.
- Never output a weighted average or per-section weight_pct yourself — that is computed
  downstream from {ats_criteria}; you only ever report score/note per section.
- Never mark a section as having no scorable data just because it's easier — score 0% honestly
  if the JD implies it and the CV has nothing, so it counts in full at its assigned weight.
- Never credit a certification that is not industry-recognized (Step 2.5) — but do NOT apply that
  same bar to Education; score Education against the JD's literal wording (Step 4).
- Never leave a requirement_matching row untagged or default its category to "skills" without
  checking — a degree requirement is "education", not "skills".
- Never output PASS/FAIL — use QUALIFIED / UNDERQUALIFIED / OVERQUALIFIED only.
- Never output prose, headers, or explanation outside the single JSON object.
- When any inference is used (parent skill, alternative skill, relevance filtering judgment),
  mark confidence MEDIUM or LOW so a human reviewer can verify it.
"""


# ============================================================
# Deterministic scoring (never trust the model's own arithmetic)
# ============================================================


def _score_requirements(
    items: list[_RequirementMatchLLM],
) -> tuple[list[RequirementMatchResult], dict[str, float | None], dict[str, tuple[int, int] | None]]:
    """Score every requirement row, then group by category (Part B.3).

    Returns (flat results list, {category: score_pct or None}, {category: (matched, total) or None}).
    "skills" pct/counts here are authoritative for the Skills weightage category. The other 4
    categories' pct/counts are informational only — section_matching stays the authoritative
    score source for Projects/Certifications/Education/Achievements (see _score_ats_output) since
    not every JD itemizes those into individual requirement rows.
    """
    results: list[RequirementMatchResult] = []
    # "not_required" rows (present in CV but tied to no requirement) score 0 and are excluded from
    # the percentage/count entirely — they must not add nor subtract, per the prompt's Step 5 table.
    scored_by_category: dict[str, list[float]] = {c: [] for c in _REQUIREMENT_CATEGORIES}
    matched_by_category: dict[str, int] = {c: 0 for c in _REQUIREMENT_CATEGORIES}
    for item in items:
        score = _MATCH_TYPE_SCORES[item.match_type]
        results.append(
            RequirementMatchResult(
                requirement=item.requirement,
                category=item.category,
                candidate_evidence=item.candidate_evidence,
                match_type=item.match_type,
                exceeds_requirement=item.match_type == "exceeds",
                score=score,
                confidence=item.confidence,
                reason=item.reason,
            )
        )
        if item.match_type != "not_required":
            scored_by_category[item.category].append(score)
            if item.match_type != "not_found":
                matched_by_category[item.category] += 1

    pct_by_category: dict[str, float | None] = {}
    counts_by_category: dict[str, tuple[int, int] | None] = {}
    for category, scores in scored_by_category.items():
        if not scores:
            pct_by_category[category] = None
            counts_by_category[category] = None
        else:
            pct_by_category[category] = sum(scores) / (len(scores) * _REQUIREMENT_MAX_SCORE) * 100
            counts_by_category[category] = (matched_by_category[category], len(scores))

    return results, pct_by_category, counts_by_category


_RESPONSIBILITY_SCORES: dict[str, float] = {"direct": 1.0, "close": 0.5, "not_found": 0.0}


def _seniority_pct(exp: _RelevantExperienceLLM) -> float:
    if exp.status == "qualified":
        return 100.0
    req, cand = exp.required_years, exp.candidate_relevant_years
    if req and cand and req > 0 and cand > 0:
        if exp.status == "underqualified":
            return max(0.0, min(cand / req, 0.95)) * 100
        return max(0.0, min(req / cand, 0.95)) * 100  # overqualified
    return {"underqualified": 30.0, "overqualified": 50.0}[exp.status]


def _score_relevant_experience(
    exp: _RelevantExperienceLLM,
) -> tuple[RelevantExperienceResult, float, tuple[int, int] | None]:
    seniority_pct = _seniority_pct(exp)

    responsibilities = exp.responsibility_matches
    if responsibilities:
        resp_results = [
            ResponsibilityMatchResult(
                requirement=r.requirement,
                evidence=r.evidence,
                match_type=r.match_type,
                score=_RESPONSIBILITY_SCORES[r.match_type],
            )
            for r in responsibilities
        ]
        responsibilities_pct = sum(r.score for r in resp_results) / len(resp_results) * 100
        # Same 30/70 blend the pre-rewrite scorer used: years/seniority match is a coarser signal,
        # itemized responsibility evidence is weighted higher since it's more directly verifiable.
        category_pct = seniority_pct * 0.3 + responsibilities_pct * 0.7
        matched = sum(1 for r in resp_results if r.match_type != "not_found")
        counts: tuple[int, int] | None = (matched, len(resp_results))
    else:
        resp_results = []
        category_pct = seniority_pct
        counts = None

    result = RelevantExperienceResult(
        job_role_required=exp.job_role_required,
        included_experience=exp.included_experience,
        excluded_experience=exp.excluded_experience,
        required_years=exp.required_years,
        candidate_relevant_years=exp.candidate_relevant_years,
        status=exp.status,
        responsibility_matches=resp_results,
    )
    return result, category_pct, counts


def _score_sections(items: list[_SectionMatchLLM]) -> tuple[list[SectionMatchResult], dict[str, float | None]]:
    results = [
        SectionMatchResult(
            section=i.section,
            jd_requires_section=i.jd_requires_section,
            cv_has_content=i.cv_has_content,
            score=i.score,
            note=i.note,
        )
        for i in items
    ]
    # A section absent from the LLM's output (JD never implied it) has no scorable data — same
    # "None" convention as an empty list used to mean under the old per-category scorers.
    pct_by_section: dict[str, float | None] = {"projects": None, "certifications": None, "education": None, "achievements": None}
    for i in items:
        pct_by_section[i.section] = i.score
    return results, pct_by_section


def _overqualification_ratio(exp: RelevantExperienceResult) -> float | None:
    """Ratio used for the Axis-2 overqualify_threshold comparison (Part A).

    required_years > 0: candidate_relevant_years / required_years — e.g. 2.0 means the candidate
    has double the required years. required_years is 0/None (e.g. "fresh graduates welcome"
    postings — edge case a): a years ratio is meaningless, so fall back to the LLM's own
    qualitative status judgment — treat "overqualified" as a fixed 2.0 (i.e. always exceeds any
    threshold >= 2.0, never exceeds a threshold below that isn't meaningful for a title/seniority
    gap anyway) and anything else as 1.0 (never overqualified).
    """
    req, cand = exp.required_years, exp.candidate_relevant_years
    if req and req > 0 and cand is not None:
        return cand / req
    return 2.0 if exp.status == "overqualified" else 1.0


def _score_ats_output(
    llm_result: _ATSLLMOutput,
    category_weights: dict[str, float],
    selected_sections: set[str] | None,
    qualify_threshold: float,
    overqualify_threshold: float | None,
    auto_reject_overqualified: bool,
) -> ATSCheckResult:
    requirement_matching, req_pct_by_category, req_counts_by_category = _score_requirements(
        llm_result.requirement_matching
    )
    relevant_experience, experience_pct, experience_counts = _score_relevant_experience(
        llm_result.relevant_experience
    )
    section_matching, section_pct_by_section = _score_sections(llm_result.section_matching)

    # category_weights comes from the recruiter's ats_criteria (or _CATEGORY_WEIGHTS for legacy
    # jobs) and is never redistributed — a category with no scorable data simply scores 0% but
    # keeps its assigned weight; a category the recruiter didn't select gets weight 0.
    category_pct: dict[str, float | None] = {
        "experience": experience_pct,
        "skills": req_pct_by_category["skills"],
        "projects": section_pct_by_section["projects"],
        "certifications": section_pct_by_section["certifications"],
        "education": section_pct_by_section["education"],
        "achievements": section_pct_by_section["achievements"],
    }
    # Skills' count comes straight from itemized rows; the other 4 use itemized counts only when
    # the JD had explicit sub-requirements in that section (else None — just the holistic score).
    counts: dict[str, tuple[int, int] | None] = {
        "experience": experience_counts,
        "skills": req_counts_by_category["skills"],
        "projects": req_counts_by_category["projects"],
        "certifications": req_counts_by_category["certifications"],
        "education": req_counts_by_category["education"],
        "achievements": req_counts_by_category["achievements"],
    }

    categories: dict[str, ATSCategoryScore] = {}
    weighted_average = 0.0
    for key in _CATEGORY_WEIGHTS:
        weight_pct = category_weights.get(key, 0.0)
        pct = category_pct[key] or 0.0
        weighted_score = weight_pct / 100 * pct
        weighted_average += weighted_score
        matched_count, total_count = counts[key] if counts[key] else (None, None)
        categories[key] = ATSCategoryScore(
            score_pct=pct,
            weight_pct=weight_pct,
            weighted_score=weighted_score,
            included=selected_sections is None or key in selected_sections,
            matched_count=matched_count,
            total_count=total_count,
        )

    # ---- Part A: two independent axes ----
    # Axis 1 — PASS/FAIL vs the recruiter's qualify_threshold. Pure weighted_average comparison.
    pass_fail: Literal["PASS", "FAIL"] = "PASS" if weighted_average >= qualify_threshold else "FAIL"

    # Axis 2 — overqualification flag, entirely independent of weighted_average/pass_fail math.
    # Never set unless the recruiter explicitly configured overqualify_threshold (edge case e:
    # threshold set without auto_reject_overqualified explicitly set never assumes True).
    is_overqualified = False
    if overqualify_threshold is not None:
        ratio = _overqualification_ratio(relevant_experience)
        is_overqualified = ratio is not None and ratio >= overqualify_threshold

    # Axis 2 can override Axis 1, never the reverse (edge case c: a PASS with is_overqualified=True
    # and auto_reject_overqualified=False stays PASS — overqualification is informational only).
    override_reason: str | None = None
    if is_overqualified and auto_reject_overqualified:
        final_verdict: Literal["PASS", "FAIL"] = "FAIL"
        override_reason = "overqualified"
    else:
        final_verdict = pass_fail

    weightage = ATSWeightage(
        experience=categories["experience"],
        skills=categories["skills"],
        projects=categories["projects"],
        certifications=categories["certifications"],
        education=categories["education"],
        achievements=categories["achievements"],
        weighted_average=weighted_average,
        qualify_threshold=qualify_threshold,
        pass_fail=pass_fail,
    )

    return ATSCheckResult(
        verdict=llm_result.verdict,
        verdict_summary=llm_result.verdict_summary,
        weightage=weightage,
        requirement_matching=requirement_matching,
        relevant_experience=relevant_experience,
        section_matching=section_matching,
        grace_credits=[GraceCredit(item=g.item, points=g.points, note=g.note) for g in llm_result.grace_credits],
        additional_cv_content=llm_result.additional_cv_content,
        is_overqualified=is_overqualified,
        final_verdict=final_verdict,
        override_reason=override_reason,
    )


_TRANSIENT_LLM_ERRORS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


@traceable(name="ats_scoring_prompt", run_type="llm")
async def _invoke_ats_llm(structured_llm, messages):
    """Isolates the LLM call so retries only apply to transient network/API errors
    (timeout, rate-limit, connection, 5xx) — validation errors from a malformed response
    are a different failure class and must propagate immediately, not retry.
    """
    delays = (2, 4)
    for attempt in range(3):
        try:
            return await structured_llm.ainvoke(messages)
        except _TRANSIENT_LLM_ERRORS as exc:
            logger.warning("ATS: transient LLM error on attempt %d/3: %s", attempt + 1, exc)
            if attempt == 2:
                raise
            await asyncio.sleep(delays[attempt])


@dataclass
class _ATSFetchResult:
    """Raw data pulled from the DB for one ATS check — candidate + job + weighting config."""
    candidate_bio: str | None
    experience_level: str | None
    candidate_role: str | None
    candidate_skills: list[str]
    experience_level_name: str
    job_role: str
    job_description: str | None
    ats_criteria_json: str | None
    required_skills_rows: list
    candidate_lookup_s: float
    job_lookup_s: float


@dataclass
class _ATSWeightConfig:
    category_weights: dict[str, float]
    selected_sections: set[str] | None
    qualify_threshold: float
    overqualify_threshold: float
    auto_reject_overqualified: bool


def _fetch_ats_data(
    candidate_id: str, job_posting_id: str, parsed_text: str | None
) -> _ATSFetchResult:
    """Blocking DB read — run via asyncio.to_thread so it doesn't block the event loop.

    Candidate bio/skills are only looked up when no parsed CV text is available (edge
    case: candidate applied without a CV — fall back to profile/skills data instead).
    """
    candidate_bio = experience_level = candidate_role = None
    candidate_skills: list[str] = []
    candidate_lookup_s = 0.0

    with db_cursor() as (conn, cur):
        if parsed_text is None:
            t_candidate_start = time.monotonic()
            cur.execute(
                """
                SELECT cp.bio, el.name, jr.title
                FROM CandidateProfiles cp
                LEFT JOIN ExperienceLevels el ON el.id = cp.experience_level_id
                LEFT JOIN JobRoles jr ON jr.id = cp.job_role_id
                WHERE cp.id = ?
                """,
                candidate_id,
            )
            candidate_row = cur.fetchone()
            if not candidate_row:
                logger.warning("ATS: candidate profile not found for candidate_id=%s", candidate_id)
                raise ValueError(f"Candidate profile not found for candidate_id={candidate_id}")

            candidate_bio, experience_level, candidate_role = candidate_row

            cur.execute(
                """
                SELECT ss.name
                FROM CandidateSkills cs
                JOIN SkillSets ss ON ss.id = cs.skill_id
                WHERE cs.candidate_id = ?
                """,
                candidate_id,
            )
            candidate_skills = [r[0] for r in cur.fetchall()]
            candidate_lookup_s = time.monotonic() - t_candidate_start

        t_job_start = time.monotonic()
        cur.execute(
            """
            SELECT el.name, jr.title, jp.description, jp.ats_criteria
            FROM JobPostings jp
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            JOIN ExperienceLevels el ON el.id = jp.experience_level_id
            WHERE jp.id = ?
            """,
            job_posting_id,
        )
        job_row = cur.fetchone()
        if not job_row:
            logger.warning("ATS: job posting not found for job_posting_id=%s", job_posting_id)
            raise ValueError(f"Job posting not found for job_posting_id={job_posting_id}")

        experience_level_name, job_role, job_description, ats_criteria_json = job_row

        cur.execute(
            """
            SELECT ss.name, jrs.proficiency_level, jrs.is_mandatory
            FROM JobRequiredSkills jrs
            JOIN SkillSets ss ON ss.id = jrs.skill_id
            WHERE jrs.job_id = ?
            """,
            job_posting_id,
        )
        required_skills_rows = cur.fetchall()
        job_lookup_s = time.monotonic() - t_job_start

    return _ATSFetchResult(
        candidate_bio=candidate_bio,
        experience_level=experience_level,
        candidate_role=candidate_role,
        candidate_skills=candidate_skills,
        experience_level_name=experience_level_name,
        job_role=job_role,
        job_description=job_description,
        ats_criteria_json=ats_criteria_json,
        required_skills_rows=required_skills_rows,
        candidate_lookup_s=candidate_lookup_s,
        job_lookup_s=job_lookup_s,
    )


def _resolve_ats_weighting(ats_criteria_json: str | None) -> _ATSWeightConfig:
    """Legacy jobs posted before recruiter-defined ATS weighting (ats_criteria IS NULL, or
    malformed) keep the original hardcoded _CATEGORY_WEIGHTS behavior exactly, all sections
    included, and default thresholds (edge case d — never crash, never auto-fail for a
    missing config)."""
    parsed = parse_ats_criteria(ats_criteria_json)
    if parsed.has_config:
        category_weights: dict[str, float] = {c["section"]: c["weight"] for c in parsed.criteria}
        selected_sections: set[str] | None = set(category_weights.keys())
    else:
        category_weights = _CATEGORY_WEIGHTS
        selected_sections = None
    return _ATSWeightConfig(
        category_weights=category_weights,
        selected_sections=selected_sections,
        qualify_threshold=parsed.qualify_threshold,
        overqualify_threshold=parsed.overqualify_threshold,
        # Edge case e: threshold set without the flag never assumes True (handled by
        # parse_ats_criteria's bool(...get(..., False)) default).
        auto_reject_overqualified=parsed.auto_reject_overqualified,
    )


def _build_ats_prompt(
    fetched: _ATSFetchResult, parsed_text: str | None, weight_config: _ATSWeightConfig
) -> tuple[str, str]:
    """Pure string assembly — no I/O. Returns (system_prompt, user_message)."""
    required_skills_str = (
        ", ".join(
            f"{name} ({level or 'any level'}){' [required]' if mandatory else ''}"
            for name, level, mandatory in fetched.required_skills_rows
        )
        if fetched.required_skills_rows
        else "Not specified"
    )

    if parsed_text:
        candidate_section = f"Candidate CV (full text — read for experience, projects, and skills):\n{parsed_text[:6000]}"
    else:
        candidate_skills_str = ", ".join(fetched.candidate_skills) if fetched.candidate_skills else "Not specified"
        candidate_section = f"""Candidate Profile (no CV uploaded — use this instead):
- Background: {fetched.candidate_bio or 'Not provided'}
- Experience Level: {fetched.experience_level or 'Not specified'}
- Current Role: {fetched.candidate_role or 'Not specified'}
- Skills: {candidate_skills_str}"""

    designation = f"{fetched.experience_level_name} {fetched.job_role}"
    job_posting_section = f"""Job Posting:
- Title: {designation}
- Required Experience Level: {fetched.experience_level_name}
- Role: {fetched.job_role}
- Full Description: {(fetched.job_description or 'Not specified')[:3000]}
- Required Skills: {required_skills_str}"""

    ats_criteria_block = "\n".join(
        f"- {_CATEGORY_LABELS[section]} ({section}) ... {weight}%"
        for section, weight in weight_config.category_weights.items()
    )

    current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system_prompt = (
        _SYSTEM_PROMPT.replace("{current_date}", current_date_str)
        .replace("{job_post_data}", job_posting_section)
        .replace("{candidate_cv_data}", candidate_section)
        .replace("{ats_criteria}", ats_criteria_block)
    )

    user_message = f"""{candidate_section}

{job_posting_section}

Assess this candidate against this job posting per the instructions."""

    return system_prompt, user_message


async def _call_ats_llm(
    system_prompt: str,
    user_message: str,
    candidate_id: str,
    job_posting_id: str,
    application_id: str | None,
) -> _ATSLLMOutput:
    """Invoke the ATS LLM and validate its output.

    Raises ATSValidationError on schema mismatch — malformed output must never reach the
    caller as a duck-typed near-miss.
    """
    structured_llm = get_llm().with_structured_output(_ATSLLMOutput)

    for attempt in range(3):
        try:
            llm_result = await _invoke_ats_llm(
                structured_llm,
                [
                    ("system", system_prompt),
                    ("user", user_message),
                ],
                langsmith_extra={
                    "metadata": {
                        "job_posting_id": job_posting_id,
                        "application_id": application_id,
                        "model_version": settings.OPENAI_MODEL,
                    }
                },
            )
        except ValidationError as exc:
            logger.error(
                "ATS: LLM output failed schema validation for candidate=%s job=%s: %s", candidate_id, job_posting_id, exc
            )
            raise ATSValidationError(f"ATS LLM output failed validation: {exc}") from exc
        except Exception as exc:
            logger.error("ATS: LLM eligibility check failed for candidate=%s job=%s: %s", candidate_id, job_posting_id, exc)
            raise

        # Explicit strict-validation gate: with_structured_output already coerces into _ATSLLMOutput
        # under the hood, but depending on provider/mode it can hand back a bare dict instead of
        # raising on a schema mismatch — re-validate explicitly so malformed output never slips
        # through as a duck-typed object that happens to have the right attributes.
        if isinstance(llm_result, _ATSLLMOutput):
            return llm_result

        try:
            return _ATSLLMOutput.model_validate(llm_result)
        except ValidationError as exc:
            if attempt < 2:
                logger.warning(
                    "ATS: LLM output failed schema validation on attempt %d/3 for candidate=%s job=%s: %s",
                    attempt + 1,
                    candidate_id,
                    job_posting_id,
                    exc,
                )
                continue
            logger.error(
                "ATS: LLM output failed schema validation for candidate=%s job=%s: %s", candidate_id, job_posting_id, exc
            )
            raise ATSValidationError(f"ATS LLM output failed validation: {exc}") from exc


async def check_ats_eligibility(
    candidate_id: str,
    job_posting_id: str,
    parsed_text: str | None = None,
    application_id: str | None = None,
) -> tuple[ATSCheckResult, str]:
    """Returns (ATSCheckResult, model_version) — model_version is the LLM identifier that
    produced this result (`settings.OPENAI_MODEL`), for audit-trail persistence.
    """
    t_start = time.monotonic()

    fetched = await asyncio.to_thread(_fetch_ats_data, candidate_id, job_posting_id, parsed_text)
    weight_config = _resolve_ats_weighting(fetched.ats_criteria_json)

    logger.info(
        "ATS timing: candidate_lookup=%.3fs job_lookup=%.3fs (candidate=%s job=%s)",
        fetched.candidate_lookup_s,
        fetched.job_lookup_s,
        candidate_id,
        job_posting_id,
    )

    system_prompt, user_message = _build_ats_prompt(fetched, parsed_text, weight_config)

    t_llm_start = time.monotonic()
    llm_result = await _call_ats_llm(system_prompt, user_message, candidate_id, job_posting_id, application_id)
    llm_call_s = time.monotonic() - t_llm_start
    logger.info(
        "ATS timing: llm_call=%.3fs (candidate=%s job=%s)", llm_call_s, candidate_id, job_posting_id
    )

    result = _score_ats_output(
        llm_result,
        weight_config.category_weights,
        weight_config.selected_sections,
        weight_config.qualify_threshold,
        weight_config.overqualify_threshold,
        weight_config.auto_reject_overqualified,
    )
    total_s = time.monotonic() - t_start
    logger.info(
        "ATS timing: total=%.3fs (candidate_lookup=%.3fs job_lookup=%.3fs llm_call=%.3fs) (candidate=%s job=%s)",
        total_s,
        fetched.candidate_lookup_s,
        fetched.job_lookup_s,
        llm_call_s,
        candidate_id,
        job_posting_id,
    )
    return result, settings.OPENAI_MODEL
