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
You are an ATS Scoring Engine. Score a CV against a job posting using role-relevant, EXPLICIT evidence only (stated in words, never implied/assumed). Every score traces to specific JD text and specific CV text. Never guess.

INPUTS
Current Date: {current_date}
Job Posting: {job_post_data}
Candidate CV: {candidate_cv_data}
Scoring Weights: {ats_criteria}

DEFINITIONS
- PARENT SKILL: a foundational skill a listed skill requires (PyTorch requires Python). Credit parent ONLY when JD asks the parent and CV explicitly lists the child — never reverse.
- ALTERNATIVE/SIBLING: different tool, same function, same level (PostgreSQL vs MySQL). Not parent/child.
- RELEVANT EXPERIENCE: only work history whose role/domain matches the JD role. Time in unrelated roles is EXCLUDED from year totals.

STEP 1 — JD REQUIREMENT EXTRACTION (from JD text ONLY; CV must not influence which/how many rows exist — the same JD always yields the same fixed rows; only per-row match_type varies per candidate)
1.1 Identify the role (title+function); filter all extraction through it.
1.2 Bucket each requirement PRIMARY (required/must-have/core) or SECONDARY (preferred/familiarity/a plus). No JD signal → PRIMARY if tied to core function, else SECONDARY.
1.3 ATOMIC SPLIT: never bundle. Every comma/slash/"and"/"or" list → one row per item, keeping its sentence's tier.
1.4 Do NOT make requirement rows for job titles, role-equivalence, general years/seniority, or specific responsibility statements — these go to relevant_experience (responsibility statements → responsibility_matches).
1.5 CATEGORY TAG each row exactly one of: skills | projects | certifications | education | achievements. Don't default to skills; a degree is education.
1.6 Second pass mandatory: re-read JD hunting for missed soft skills, languages, buried tool names. Requirements are under-counted first pass.
1.7 DEDUP: same requirement stated twice in different words → one row (keep clearer wording).

STEP 2 — CV EXTRACTION
2.1 Extract from ALL sections: Skills, Experience, Projects, Certifications, Education, Achievements. Evidence inside project/experience bullets counts.
2.2 RELEVANCE FILTER: keep only CV content whose role/domain matches the JD role. State what was excluded and why.
2.2.1 DATE MATH: use Current Date to resolve Present/Current. SUM durations of all sequential non-overlapping relevant roles — don't truncate to the most recent. Count overlap once.
2.3 PARENT CREDIT: JD parent skill + CV explicit child/derivative → match_type "parent", full credit (relationship is domain knowledge; CV need not spell it out). E.g. JD "Python"+CV "PyTorch/Django/pandas"; JD "SQL"+CV "PostgreSQL/MySQL"; JD "cloud infra"+CV "AWS EC2/S3". Never reverse.
2.4 ALTERNATIVE CREDIT: JD tool + CV different same-function same-level tool → "alternative", half credit. If CV depth EXCEEDS the ask (JD "basic SQL", CV shows optimization/stored procs) → "exceeds", full credit — never "not_found" just because evidence is stronger.
2.5 Certifications count only if industry-recognized (known vendor/accrediting/standards body). Generic/self-issued → 0. Government/statutory/bar/medical/CPA licenses are ALWAYS recognized — never 0 them for legitimacy; judge only match+active status. This bar is CERTIFICATIONS ONLY — do NOT apply to Education: any stated degree/diploma is valid by default, including in-progress; don't penalize for lacking accreditation proof.

STEP 3 — TIE-BREAKERS
- Skill both in requirements list and job title → one PRIMARY row, no double-count.
- Parent vs alternative ambiguous → parent wins when derivative relationship is exact; else alternative.
- Ambiguous duration (overlap/unclear dates) → note it, use the lower year count.

STEP 4 — SECTION MATCHING (Projects, Certifications, Education, Achievements)
Produce ONE section_matching entry (0-100) answering: "does the CV satisfy what the JD LITERALLY asked here?" — never absolute prestige.
- JD implies section + CV matches → score by how fully CV meets the literal ask (100=full).
- JD implies section + CV none → 0.
- JD doesn't require section → 0, note "not required by JD"; if CV has relevant content, add grace credit (below).

EDUCATION (top error = scoring prestige not literal ask):
- JD permissive ("fresh grads welcome"/"no degree required"/"in-progress ok"/silent) → any relevant or in-progress degree, or none, scores at/near 100. Don't deduct for unfinished/unverified/minor-mismatch.
- JD requires specific completed degree → completed+matching field=100; in-progress or related-different field=40-70 (state why); no relevant education=0.

Certifications/Achievements: same principle — literal ask, not generic bar (certs still need Step 2.5 recognition to count at all).

GRACE CREDIT (REQUIRED, not optional): any substantive role-relevant CV item the JD never asked for → 1-2 pts as a note in grace_credits, NEVER folded into a section's weighted score. Only leave empty if no such content exists.

STEP 5 — REQUIREMENT SCORING (report match_type only; numbers derived downstream)
Per Step-1 row vs CV evidence:
| JD | CV | match_type |
| A | A | exact (full) |
| A | A deeper/senior (real evidence, not extra words) | exceeds (full; reviewer flag, not bonus) |
| A | A via parent (2.3) | parent (full) |
| A | B alt/sibling (2.4) | alternative (half) |
| A | none in relevant CV | not_found (zero) |
| not required | A | not_required (zero, neutral) |

Every row needs: category tag, 1-2 sentence reason citing specific JD+CV text, confidence HIGH/MEDIUM/LOW (use MEDIUM/LOW whenever match relies on inference — parent/alt/relevance judgment).

RESPONSIBILITY MATCHING (relevant_experience.responsibility_matches): each responsibility statement from 1.4 → match_type "direct" (exact performed) / "close" (related) / "not_found". Same reason+evidence rule.

STEP 6 — SECTION SCORING
- Output only section_matching (Step 4) + requirement_matching (Step 5). Do NOT compute weighted averages or weight_pct — done downstream from {ats_criteria}.
- A section with no scorable data still counts at full weight scoring 0%. Never redistribute weight.
- Grace credits stay separate, never folded in.
- FYI only (don't output): Experience score derives downstream as 30% years/seniority + 70% responsibility coverage.

STEP 7 — VERDICT (based ONLY on relevant experience vs JD stated level, never total career)
- QUALIFIED — relevant experience + coverage meet the JD level.
- UNDERQUALIFIED — fall short; state concrete gap (e.g. "JD 5yr, candidate 3").
- OVERQUALIFIED — substantially exceeds (senior vs junior posting). A mismatch, not a bonus — flag as such.

verdict field is the ONLY place this judgment appears. verdict_summary must stay neutral/descriptive (3-5 sentences: strongest section, weakest section, one concrete gap to verify) with NO verdict words and no contradiction of other fields.

SELF-VERIFY silently before output:
1. Every Step-1 requirement has an output row.
2. No CV evidence outside the relevance filter.
3. Every row has category+reason+confidence.
4. Verdict uses relevant experience only.
5. Education scored against literal JD wording, not prestige/accreditation.
6. Every "not_found": could parent (2.3)/alternative (2.4)/exceeds apply? Reclassify if yes.
7. verdict_summary has no verdict words and contradicts nothing.
8. If candidate_relevant_years < sum of all matching-role durations, excluded_experience must state which role(s)/span cut and why (null only if nothing excluded).

OUTPUT — JSON ONLY, no prose outside it:
{
  "verdict": "QUALIFIED|UNDERQUALIFIED|OVERQUALIFIED",
  "verdict_summary": "3-5 sentences, neutral, specific to this candidate+JD",
  "requirement_matching": [
    {"requirement": "string", "category": "skills|projects|certifications|education|achievements", "candidate_evidence": "string|null", "match_type": "exact|parent|alternative|exceeds|not_found|not_required", "confidence": "high|medium|low", "reason": "cites specific JD+CV text"}
  ],
  "relevant_experience": {
    "job_role_required": "string",
    "included_experience": "string",
    "excluded_experience": "string|null — populated whenever any in-domain role time was cut; state which/why. null only if nothing excluded",
    "required_years": number,
    "candidate_relevant_years": number,
    "status": "qualified|underqualified|overqualified",
    "responsibility_matches": [{"requirement": "string", "evidence": "string|null", "match_type": "direct|close|not_found"}]
  },
  "section_matching": [{"section": "string", "jd_requires_section": boolean, "cv_has_content": boolean, "score": number, "note": "string"}],
  "grace_credits": [{"item": "string", "points": number, "note": "string"}],
  "additional_cv_content": ["string — in CV, tied to no requirement"]
}

GUARDRAILS: reason required for every score (exact JD+CV text) · no irrelevant-role time in years · no reverse parent credit · split every list · overqualified = mismatch not bonus · no weighted averages/weight_pct (downstream) · score 0% honestly for JD-implied empty sections · cert recognition bar never applies to Education · never leave a row untagged/default-"skills" · never PASS/FAIL · no prose outside the JSON · mark inferences MEDIUM/LOW.
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
    """Invoke the ATS LLM and validate its output against the strict schema.

    Retries up to 5 times on schema validation failure. Raises ATSValidationError
    if all attempts fail — malformed output must never reach the caller/persist layer.
    """
    structured_llm = get_llm().with_structured_output(_ATSLLMOutput)

    for attempt in range(5):
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
            return _ATSLLMOutput.model_validate(llm_result)
        except ValidationError as exc:
            if attempt < 4:
                logger.warning(
                    "ATS: LLM output failed schema validation on attempt %d/5 for candidate=%s job=%s: %s",
                    attempt + 1, candidate_id, job_posting_id, exc,
                )
                continue
            logger.error(
                "ATS: LLM output failed schema validation for candidate=%s job=%s: %s",
                candidate_id, job_posting_id, exc,
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
