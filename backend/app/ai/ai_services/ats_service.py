import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_llm
from app.database import get_connection

logger = logging.getLogger(__name__)

_CATEGORY_WEIGHTS: dict[str, float] = {
    "experience": 30,
    "skills": 35,
    "projects": 20,
    "certifications": 5,
    "education": 5,
    "achievements": 5,
}

_PASS_THRESHOLD = 65

_TIER_WEIGHTS: dict[str, float] = {"primary": 1.0, "secondary": 0.5, "tertiary": 0.2}
_TIER_ORDER: dict[str, int] = {"primary": 0, "secondary": 1, "tertiary": 2}
_ALTERNATIVE_DOWNGRADE: dict[str, float] = {"primary": 0.5, "secondary": 0.2, "tertiary": 0.0}
_RESPONSIBILITY_SCORES: dict[str, float] = {"direct": 1.0, "close": 0.5, "not_found": 0.0}
_CERTIFICATION_SCORES: dict[tuple[bool, str], float] = {
    (True, "industry_recognized"): 1.0,
    (True, "not_recognized"): 0.5,
    (False, "industry_recognized"): 0.5,
    (False, "not_recognized"): 0.0,
}


# ============================================================
# Raw LLM output schema — the model extracts and classifies evidence;
# all numeric scores are then derived deterministically in Python
# rather than trusted from the model's own arithmetic.
# ============================================================


class _SkillMatchLLM(BaseModel):
    requirement: str
    tier: Literal["primary", "secondary", "tertiary"]
    candidate_skill: str | None = None
    match_type: Literal["exact", "alternative", "not_found"]
    note: str


class _SeniorityMatch(BaseModel):
    required: str
    candidate: str
    status: Literal["match", "underqualified", "overqualified"]
    note: str


class _YearsMatch(BaseModel):
    required_years: float | None = None
    candidate_years: float | None = None


class _ResponsibilityMatchLLM(BaseModel):
    requirement: str
    evidence: str | None = None
    match_type: Literal["direct", "close", "not_found"]


class _ExperienceMatchingLLM(BaseModel):
    seniority: _SeniorityMatch
    years: _YearsMatch
    responsibilities: list[_ResponsibilityMatchLLM] = Field(default_factory=list)


class _ProjectMatchLLM(BaseModel):
    project_name: str
    complexity: float = Field(ge=0, le=1)
    technologies: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    note: str


class _CertificationMatchLLM(BaseModel):
    certification: str
    matches_requirement: bool
    recognition: Literal["industry_recognized", "not_recognized"]


class _EducationMatchingLLM(BaseModel):
    relevant: bool
    note: str


class _AchievementMatchLLM(BaseModel):
    achievement: str
    relevant: bool
    required: bool


class _ATSLLMOutput(BaseModel):
    """Raw structured output requested from the LLM — extraction + classification only.

    Category scores, weighted contributions, and the final PASS/FAIL verdict are computed
    deterministically in Python from this data (see `_score_ats_output`).
    """

    verdict_summary: str = Field(
        description="3-5 sentence summary: pass/fail, strongest category, weakest category, and one "
        "concrete reason a human reviewer should double-check."
    )
    skill_matching: list[_SkillMatchLLM] = Field(default_factory=list)
    experience_matching: _ExperienceMatchingLLM
    projects_matching: list[_ProjectMatchLLM] = Field(default_factory=list)
    certifications_matching: list[_CertificationMatchLLM] = Field(default_factory=list)
    education_matching: _EducationMatchingLLM
    achievements_matching: list[_AchievementMatchLLM] = Field(default_factory=list)
    additional_skills: list[str] = Field(default_factory=list)


# ============================================================
# Final response schema (deterministically computed, persisted, and returned to the API/frontend)
# ============================================================


class ATSCategoryScore(BaseModel):
    score_pct: float
    weight_pct: float
    weighted_score: float


class ATSWeightage(BaseModel):
    experience: ATSCategoryScore
    skills: ATSCategoryScore
    projects: ATSCategoryScore
    certifications: ATSCategoryScore
    education: ATSCategoryScore
    achievements: ATSCategoryScore
    weighted_average: float
    pass_threshold: int = _PASS_THRESHOLD


class SkillMatchResult(BaseModel):
    requirement: str
    tier: Literal["primary", "secondary", "tertiary"]
    candidate_skill: str | None = None
    match_type: Literal["exact", "alternative", "not_found"]
    score: float
    max_score: float
    note: str


class ResponsibilityMatchResult(BaseModel):
    requirement: str
    evidence: str | None = None
    match_type: Literal["direct", "close", "not_found"]
    score: float


class ExperienceMatchingResult(BaseModel):
    seniority: _SeniorityMatch
    years: _YearsMatch
    responsibilities: list[ResponsibilityMatchResult] = Field(default_factory=list)


class ProjectMatchResult(BaseModel):
    project_name: str
    complexity: float
    technologies: float
    impact: float
    relevance: float
    total: float
    max: float = 4.0
    note: str


class CertificationMatchResult(BaseModel):
    certification: str
    matches_requirement: bool
    recognition: Literal["industry_recognized", "not_recognized"]
    score: float


class EducationMatchingResult(BaseModel):
    relevant: bool
    score: float
    note: str


class AchievementMatchResult(BaseModel):
    achievement: str
    relevant: bool
    required: bool
    score: float


class ATSCheckResult(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    verdict_summary: str
    weightage: ATSWeightage
    skill_matching: list[SkillMatchResult] = Field(default_factory=list)
    experience_matching: ExperienceMatchingResult
    projects_matching: list[ProjectMatchResult] = Field(default_factory=list)
    certifications_matching: list[CertificationMatchResult] = Field(default_factory=list)
    education_matching: EducationMatchingResult
    achievements_matching: list[AchievementMatchResult] = Field(default_factory=list)
    additional_skills: list[str] = Field(default_factory=list)


_SYSTEM_PROMPT = """You are an ATS Scoring Engine. You evaluate a candidate's CV against a job posting
using a strict, weighted, evidence-based scoring model. You never guess or infer a skill/requirement is
satisfied unless there is direct, explicit evidence in the CV.

========================
1. SYSTEM OVERVIEW
========================

Core Principle:
Every requirement in the job posting (technical skills, soft skills, responsibilities,
certifications, education, achievements) must be individually extracted, individually matched
against CV evidence, individually scored, then rolled up into a weighted total. Never produce a
single holistic score without the underlying breakdown — the breakdown is the primary output,
the score is derived from it. You reason about evidence like a human recruiter would — you do not
do raw keyword or exact-string matching, except where explicitly told to be strict below.

Inputs:
- Job Posting Data: {job_post_data}
- Candidate CV Text: {candidate_cv_text}

Do not silently fill gaps. If the JD lists a requirement (including generic/soft ones like
"strong math skills" or "excellent communication") and it is not explicitly named in the CV's
Skills section (see Section 2B), it is scored 0 — even if it seems "implied" by a degree title, job
title, or industry norm. Degree titles, job titles, and years of experience are not automatic
evidence for a named skill unless the requirement is explicitly about degree/education level.

========================
2. SKILL EXTRACTION
========================

A) Extraction Rules
- Extract every explicit requirement/skill from the JD — technical tools, soft skills, domain
  knowledge, and generic competencies (math, communication, problem-solving, etc.). Do not skip
  generic/soft requirements; they still get scored.
- ATOMIC REQUIREMENT RULE: never bundle multiple distinct skills into a single skill_matching
  entry. If a JD sentence lists several tools/languages/skills (comma, semicolon, "and"/"or"
  separated), split it into one skill_matching row PER skill, each with its own tier. A tier shift
  inside one sentence must be preserved per-skill — e.g. "Knowledge of R, SQL and Python;
  familiarity with Scala, Java or C++ is an asset" becomes SIX separate rows: R, SQL, Python (each
  PRIMARY) and Scala, Java, C++ (each TERTIARY, since "familiarity... is an asset" marks them as
  nice-to-have). Likewise "Understanding of machine-learning and operations research" becomes TWO
  rows: "Machine Learning" and "Operations Research".
- SKILL vs. EXPERIENCE RULE: a requirement about a job title/role ("Proven experience as a Data
  Scientist or Data Analyst"), a role-equivalence, or a general years-of-experience/seniority
  statement is NOT a skill — do not create a skill_matching row for it. It belongs in Professional
  Experience instead (Section 4B responsibilities / seniority). Only requirements naming an actual
  tool, technology, technique, domain-knowledge area, or competency (e.g. "data mining", "machine
  learning", "Python", "communication") are skills and belong in skill_matching — each as its own
  atomic row per the rule above.
- Classify each extracted skill requirement into exactly one tier:
  - PRIMARY — explicitly required, core to the role's stated responsibilities.
  - SECONDARY — explicitly required but supporting/contextual (e.g. "familiarity with X").
  - TERTIARY — mentioned as a nice-to-have, asset, or bonus.
- Before matching anything, locate the candidate's Skills / Technical Skills / Technologies
  section in the CV first and specifically. Build the candidate's skill list ONLY from the items
  listed inside that section — this list is what you match every JD requirement against in
  Sections C and D below.

B) Skill Evidence Source — Skills Section ONLY, Not the Whole CV (STRICT)
Only the candidate's explicitly named Skills / Technical Skills / Technologies section counts as
evidence for skill matching. Do NOT scan or use the rest of the CV for skill evidence — not
project descriptions, not work experience bullets, not responsibilities, not achievements, not
summaries, not any other narrative content — even if that narrative clearly demonstrates the
underlying capability. Skill matching evidence comes from that one section alone. If the CV has no
distinct Skills section, or a given skill is not explicitly listed by name inside it, every
requirement that depends on it must be marked NOT FOUND.

C) Exact / Synonym Match (full credit)
A required skill is matched only when it — or an unambiguous, standard synonym/abbreviation of that
exact same skill (e.g. "JS" = "JavaScript", "K8s" = "Kubernetes", "ML" = "Machine Learning") — is
explicitly named in the Skills section. Do NOT infer a broader/parent skill from a narrower one
that happens to be listed (e.g. do NOT credit "Python" merely because "PyTorch" is listed) — every
required skill must itself be explicitly present by name or exact synonym in the Skills section.

D) Alternative / Sibling-Skill Match (downgraded credit)
When the JD requires a specific tool and the Skills section explicitly lists a different but
comparable sibling tool at the same level (not a synonym of the same skill) — e.g. JD requires
TensorFlow, Skills section lists PyTorch — this is an ALTERNATIVE match, scored one tier below the
requirement's own tier (see Section 4A for the exact multiplier).

E) Not-Found Rule (STRICT — no benefit of the doubt)
If the required skill (or an exact synonym) is not explicitly named in the Skills section, mark it
NOT FOUND. Do not credit it based on projects, work experience, achievements, job titles, or any
other inference — even strong circumstantial evidence elsewhere in the CV does not count. When in
doubt, mark NOT FOUND, never a match.

F) Skills in CV Not Tied to Any Requirement
Skills explicitly listed in the Skills section that don't map to any JD requirement are listed
separately as "additional skills" for context. They do not add to or subtract from the weighted
score.

========================
3. WEIGHTED SCORING MODEL
========================

Category weights (source of truth):
- Professional Experience ............ 30%
- Technical & Soft Skills ............. 35%
- Projects ............................ 20%
- Certifications ...................... 5%
- Education ........................... 5%
- Achievements & Quantifiable Results . 5%

These weights are FIXED and are never redistributed or reallocated between categories. If a
category has no scorable data (e.g. no certifications listed, no projects section, no
achievements), that category's score for this candidate is simply 0 — its weight still counts in
full in the weighted average. Do not exclude a category from the total, and do not shift its
weight onto other categories.

========================
4. SCORING MECHANICS
========================

A) Skills (35% category)
Tier base weights: PRIMARY = 1.0, SECONDARY = 0.5, TERTIARY = 0.2.
For each required skill, score against the match type found:
- EXACT match → full tier weight (1.0 / 0.5 / 0.2).
- ALTERNATIVE (sibling) match → one tier down from the requirement's own tier:
  - PRIMARY requirement + alternative match → 0.5
  - SECONDARY requirement + alternative match → 0.2
  - TERTIARY requirement + alternative match → 0
- NOT FOUND → 0.
Category score = (sum of achieved scores) / (sum of max possible tier weights) × 100.

B) Professional Experience (30% category)
Split into:
- Seniority & Years Match (weight: 30% of this category) — strictly compare required seniority
  level/years vs candidate's actual years and title level. Explicitly flag QUALIFIED, UNDERQUALIFIED or
  OVERQUALIFIED, do not just say "meets requirement" — state the direction and magnitude of any
  mismatch. Significant over-qualification (e.g. a senior/staff-level candidate against a
  junior/entry-level posting) is a mismatch in the OVERQUALIFIED direction, not automatically a
  strength.
- Responsibility Match (weight: 70% of this category) — for each JD responsibility/requirement,
  find the closest CV experience evidence and score:
  - Direct match → 1.0
  - Close/partial match → 0.5
  - No match found → 0
  Domain fit is evaluated strictly as part of this responsibility matching: if the job posting
  requires experience in a specific domain (e.g. CV, NLP, LLMs/agentic AI, embedded systems,
  fintech compliance, etc.), score that domain-specific responsibility as "no match" unless the CV
  shows explicit, genuine evidence of work in that domain — general software/engineering
  experience in an unrelated domain does not satisfy a named domain requirement, no matter how
  strong the candidate otherwise is. Do not apply the alternative-match flexibility from Section 2D
  to domain or role-title fit — that applies only to individual technical/soft skills.
  Category score = (sum of achieved) / (count of responsibilities) × 100, blended with the
  seniority sub-score per the 30/70 split above.

C) Projects (20% category)
For each relevant project, score four dimensions (0–1 each, sum to a 0–4 total):
- Complexity
- Technologies used (relevance to JD stack)
- Measurable impact
- Relevance to this job's actual responsibilities
Category score = average of (project_total / 4) across all scored projects × 100.

D) Certifications (5% category)
Only include certifications that are explicitly present in the candidate's CV (e.g. listed in a
Certifications section, or explicitly named as a held credential) — never infer or assume a
certification exists.

Evaluate each listed certification on TWO INDEPENDENT axes — do not conflate them:
- `matches_requirement` (boolean) — set this to true ONLY when BOTH are true: (1) the job
  posting's requirements/description explicitly names this exact certification (or an
  unambiguous equivalent, e.g. "AWS Certified Solutions Architect" vs "AWS Solutions Architect
  Certification") as something the role requires or asks for, AND (2) the candidate's CV
  explicitly shows the candidate holds it. If the JD does NOT explicitly name/require this
  certification, `matches_requirement` MUST be false — do not set it true merely because the
  certification seems generally useful, relevant to the domain, or valuable for the role. General
  relevance is NOT sufficient; the JD must explicitly ask for it.
- `recognition` — is this an "industry_recognized" credential (issued by a well-known vendor,
  standards body, or professional organization — e.g. AWS, PMI, Google, Coursera-verified
  specializations from accredited institutions) or "not_recognized" (generic, unverifiable,
  self-issued, or from an obscure/low-credibility source)? Judge this purely on the credential's
  own credibility, independent of whether the job requires it.
A certification can be recognized but irrelevant to the job, or job-relevant but not a widely
recognized credential — score accordingly:
- matches_requirement=true AND industry_recognized → 1.0
- matches_requirement=true AND not_recognized → 0.5
- matches_requirement=false AND industry_recognized → 0.5
- matches_requirement=false AND not_recognized → 0
Category score = average across listed certifications × 100. If the candidate lists no
certifications, this category scores 0 — do not exclude it or shift its weight elsewhere.

E) Education (5% category)
- Relevant to role/domain and meets stated minimum → 1.0
- Not relevant or below stated minimum → 0

F) Achievements & Quantifiable Results (5% category)
Per achievement:
- Relevant to the role AND tied to a requirement in the JD → 1.0
- Relevant to the role OR tied to a requirement (only one of the two) → 0.5
- Neither → 0
Category score = average across listed achievements × 100.

========================
5. VERDICT & THRESHOLD
========================

- PASS_THRESHOLD = 65 (strict, no rounding leniency — 64.9 is a FAIL).
- Weighted average = sum of (category_score_pct × category_weight_pct) across all six categories,
  using the fixed weights from Section 3 — never redistributed, never excluded.
- verdict = PASS if weighted average >= PASS_THRESHOLD, else FAIL.
- Write a 3–5 sentence verdict summary: state pass/fail, the single strongest category, the
  single weakest category, and one concrete reason a human reviewer should double-check
  (especially any explicitly-named JD requirement with zero CV evidence, e.g. unmentioned math
  skills, unmentioned required tools).
- The weighted average alone determines PASS/FAIL — do not let a strong narrative in one category
  (e.g. Skills or Projects) override the computed weighted average, and do not let a high score in
  one category silently compensate for a genuine role, seniority, or domain mismatch; such
  mismatches must already be reflected in the Professional Experience category score per Section 4B.

========================
6. GUARDRAILS
========================

- Never assume a skill is satisfied by degree title, job title, or years alone unless the JD
  requirement is specifically about education/seniority.
- Never credit a skill based on project descriptions, work experience bullets, achievements, or
  any other narrative CV content — only the explicit Skills section counts as evidence (Section 2B).
- Never infer a broader/parent skill from a narrower one listed in the Skills section, or vice
  versa — every required skill must itself be explicitly named or have an exact synonym listed
  (Section 2C).
- Never omit a JD-stated requirement from skill_matching, including soft/generic skills.
- Never bundle multiple distinct skills into one skill_matching row — split every comma/"and"/"or"
  separated list of tools/languages/skills into individual atomic rows (Section 2A).
- Never put a job-title/role/general-experience requirement into skill_matching — those belong in
  Professional Experience (Section 2A, 4B).
- Never conflate certification job-relevance with certification recognition — score them as two
  independent axes (Section 4D).
- Never set a certification's `matches_requirement` to true unless the JD explicitly names/requires
  that exact certification AND the candidate's CV explicitly shows they hold it — general domain
  relevance or "this would help the role" reasoning is not sufficient (Section 4D).
- Never list a certification in certifications_matching that isn't explicitly present in the
  candidate's CV.
- Never round the weighted average up across the pass threshold.
- Never credit a requirement as matched when there is any doubt about explicit Skills-section
  evidence (Section 2E) — when in doubt, mark it NOT FOUND.
- Never redistribute a category's weight to other categories and never exclude a category from the
  weighted average — a category with no scorable data simply scores 0% for that category, using
  its normal fixed weight (Section 3).
- Never treat a role, seniority, or domain mismatch (Section 4B) as fixable by strong Skills or
  Projects scores elsewhere — score the affected responsibility/seniority sub-score low and let
  the weighting model reflect it.
- Never output prose, headers, or explanation outside the single JSON object.  

========================
7. OUTPUT FORMAT
========================

Return only this JSON structure, no prose outside it:

{
  "verdict": "PASS" | "FAIL",
  "verdict_summary": "3-5 sentence string",
  "weightage": {
    "experience": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "skills": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "projects": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "certifications": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "education": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "achievements": {"score_pct": number, "weight_pct": number, "weighted_score": number},
    "weighted_average": number,
    "pass_threshold": 65
  },
  "skill_matching": [
    {
      "requirement": "string",
      "tier": "primary" | "secondary" | "tertiary",
      "candidate_skill": "string or null",
      "match_type": "exact" | "alternative" | "not_found",
      "score": number,
      "max_score": number,
      "note": "string"
    }
  ],
  "experience_matching": {
    "seniority": {"required": "string", "candidate": "string", "status": "match" | "underqualified" | "overqualified", "note": "string"},
    "years": {"required_years": number, "candidate_years": number},
    "responsibilities": [
      {"requirement": "string", "evidence": "string or null", "match_type": "direct" | "close" | "not_found", "score": number}
    ]
  },
  "projects_matching": [
    {"project_name": "string", "complexity": number, "technologies": number, "impact": number, "relevance": number, "total": number, "max": 4, "note": "string"}
  ],
  "certifications_matching": [
    {"certification": "string", "matches_requirement": boolean, "recognition": "industry_recognized" | "not_recognized", "score": number}
  ],
  "education_matching": {"relevant": boolean, "score": number, "note": "string"},
  "achievements_matching": [
    {"achievement": "string", "relevant": boolean, "required": boolean, "score": number}
  ],
  "additional_skills": ["string"]
}

Every `note`/`verdict_summary` string must contain a specific, evidence-based explanation
referencing what was actually found (or not found) in the candidate's CV and the job posting —
never a generic or static statement.
"""


# ============================================================
# Deterministic scoring (never trust the model's own arithmetic)
# ============================================================


def _score_skills(items: list[_SkillMatchLLM]) -> tuple[list[SkillMatchResult], float | None]:
    if not items:
        return [], None
    results: list[SkillMatchResult] = []
    total_score = 0.0
    total_max = 0.0
    for item in items:
        tier_weight = _TIER_WEIGHTS[item.tier]
        if item.match_type == "not_found":
            score = 0.0
        elif item.match_type == "alternative":
            score = _ALTERNATIVE_DOWNGRADE[item.tier]
        else:
            score = tier_weight
        total_score += score
        total_max += tier_weight
        results.append(
            SkillMatchResult(
                requirement=item.requirement,
                tier=item.tier,
                candidate_skill=item.candidate_skill,
                match_type=item.match_type,
                score=score,
                max_score=tier_weight,
                note=item.note,
            )
        )
    pct = (total_score / total_max * 100) if total_max > 0 else 0.0
    # Sort by tier (primary, secondary, tertiary) — the only reordering applied; each item's own
    # tier value is copied as-is from the LLM output above and never rewritten, so this only
    # changes display order, not any skill's classification.
    results.sort(key=lambda r: _TIER_ORDER[r.tier])
    return results, pct


def _seniority_score(seniority: _SeniorityMatch, years: _YearsMatch) -> float:
    if seniority.status == "match":
        return 1.0
    req, cand = years.required_years, years.candidate_years
    if req and cand and req > 0 and cand > 0:
        if seniority.status == "underqualified":
            return max(0.0, min(cand / req, 0.95))
        return max(0.0, min(req / cand, 0.95))  # overqualified
    return {"underqualified": 0.3, "overqualified": 0.5}[seniority.status]


def _score_experience(matching: _ExperienceMatchingLLM) -> tuple[ExperienceMatchingResult, float]:
    seniority_pct = _seniority_score(matching.seniority, matching.years) * 100

    responsibilities = matching.responsibilities
    if responsibilities:
        results = [
            ResponsibilityMatchResult(
                requirement=r.requirement,
                evidence=r.evidence,
                match_type=r.match_type,
                score=_RESPONSIBILITY_SCORES[r.match_type],
            )
            for r in responsibilities
        ]
        responsibilities_pct = sum(r.score for r in results) / len(results) * 100
        category_pct = seniority_pct * 0.3 + responsibilities_pct * 0.7
    else:
        results = []
        category_pct = seniority_pct

    return (
        ExperienceMatchingResult(seniority=matching.seniority, years=matching.years, responsibilities=results),
        category_pct,
    )


def _score_projects(items: list[_ProjectMatchLLM]) -> tuple[list[ProjectMatchResult], float | None]:
    if not items:
        return [], None
    results: list[ProjectMatchResult] = []
    total_pct = 0.0
    for item in items:
        total = item.complexity + item.technologies + item.impact + item.relevance
        total_pct += total / 4 * 100
        results.append(
            ProjectMatchResult(
                project_name=item.project_name,
                complexity=item.complexity,
                technologies=item.technologies,
                impact=item.impact,
                relevance=item.relevance,
                total=total,
                note=item.note,
            )
        )
    return results, total_pct / len(items)


def _score_certifications(items: list[_CertificationMatchLLM]) -> tuple[list[CertificationMatchResult], float | None]:
    if not items:
        return [], None
    results = [
        CertificationMatchResult(
            certification=i.certification,
            matches_requirement=i.matches_requirement,
            recognition=i.recognition,
            score=_CERTIFICATION_SCORES[(i.matches_requirement, i.recognition)],
        )
        for i in items
    ]
    pct = sum(r.score for r in results) / len(results) * 100
    return results, pct


def _score_education(edu: _EducationMatchingLLM) -> tuple[EducationMatchingResult, float]:
    score = 1.0 if edu.relevant else 0.0
    return EducationMatchingResult(relevant=edu.relevant, score=score, note=edu.note), score * 100


def _score_achievements(items: list[_AchievementMatchLLM]) -> tuple[list[AchievementMatchResult], float | None]:
    if not items:
        return [], None
    results = []
    for item in items:
        if item.relevant and item.required:
            score = 1.0
        elif item.relevant or item.required:
            score = 0.5
        else:
            score = 0.0
        results.append(AchievementMatchResult(achievement=item.achievement, relevant=item.relevant, required=item.required, score=score))
    pct = sum(r.score for r in results) / len(results) * 100
    return results, pct


def _score_ats_output(llm_result: _ATSLLMOutput) -> ATSCheckResult:
    skill_matching, skills_pct = _score_skills(llm_result.skill_matching)
    experience_matching, experience_pct = _score_experience(llm_result.experience_matching)
    projects_matching, projects_pct = _score_projects(llm_result.projects_matching)
    certifications_matching, certifications_pct = _score_certifications(llm_result.certifications_matching)
    education_matching, education_pct = _score_education(llm_result.education_matching)
    achievements_matching, achievements_pct = _score_achievements(llm_result.achievements_matching)

    # Weights are fixed (_CATEGORY_WEIGHTS) and never redistributed — a category with no
    # scorable data (empty list) simply scores 0% but keeps its full normal weight.
    category_pct: dict[str, float | None] = {
        "experience": experience_pct,
        "skills": skills_pct,
        "projects": projects_pct,
        "certifications": certifications_pct,
        "education": education_pct,
        "achievements": achievements_pct,
    }

    categories: dict[str, ATSCategoryScore] = {}
    weighted_average = 0.0
    for key, weight_pct in _CATEGORY_WEIGHTS.items():
        pct = category_pct[key] or 0.0
        weighted_score = weight_pct / 100 * pct
        weighted_average += weighted_score
        categories[key] = ATSCategoryScore(score_pct=pct, weight_pct=weight_pct, weighted_score=weighted_score)

    verdict: Literal["PASS", "FAIL"] = "PASS" if weighted_average >= _PASS_THRESHOLD else "FAIL"

    weightage = ATSWeightage(
        experience=categories["experience"],
        skills=categories["skills"],
        projects=categories["projects"],
        certifications=categories["certifications"],
        education=categories["education"],
        achievements=categories["achievements"],
        weighted_average=weighted_average,
        pass_threshold=_PASS_THRESHOLD,
    )

    return ATSCheckResult(
        verdict=verdict,
        verdict_summary=llm_result.verdict_summary,
        weightage=weightage,
        skill_matching=skill_matching,
        experience_matching=experience_matching,
        projects_matching=projects_matching,
        certifications_matching=certifications_matching,
        education_matching=education_matching,
        achievements_matching=achievements_matching,
        additional_skills=llm_result.additional_skills,
    )


async def check_ats_eligibility(
    candidate_id: str,
    job_posting_id: str,
    parsed_text: str | None = None,
) -> ATSCheckResult:
    conn = get_connection()
    try:
        cur = conn.cursor()

        if parsed_text is None:
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

        cur.execute(
            """
            SELECT el.name, jr.title, jp.description
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

        experience_level_name, job_role, job_description = job_row
        designation = f"{experience_level_name} {job_role}"

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
    finally:
        conn.close()

    required_skills_str = (
        ", ".join(
            f"{name} ({level or 'any level'}){' [required]' if mandatory else ''}"
            for name, level, mandatory in required_skills_rows
        )
        if required_skills_rows
        else "Not specified"
    )

    if parsed_text:
        candidate_section = f"Candidate CV (full text — read for experience, projects, and skills):\n{parsed_text[:6000]}"
    else:
        candidate_skills_str = ", ".join(candidate_skills) if candidate_skills else "Not specified"
        candidate_section = f"""Candidate Profile (no CV uploaded — use this instead):
- Background: {candidate_bio or 'Not provided'}
- Experience Level: {experience_level or 'Not specified'}
- Current Role: {candidate_role or 'Not specified'}
- Skills: {candidate_skills_str}"""

    job_posting_section = f"""Job Posting:
- Title: {designation}
- Required Experience Level: {experience_level_name}
- Role: {job_role}
- Full Description: {(job_description or 'Not specified')[:3000]}
- Required Skills: {required_skills_str}"""

    system_prompt = _SYSTEM_PROMPT.replace("{job_post_data}", job_posting_section).replace(
        "{candidate_cv_text}", candidate_section
    )

    user_message = f"""{candidate_section}

{job_posting_section}

Assess this candidate against this job posting per the instructions."""

    structured_llm = get_llm().with_structured_output(_ATSLLMOutput)
    try:
        llm_result = await structured_llm.ainvoke(
            [
                ("system", system_prompt),
                ("user", user_message),
            ]
        )
    except Exception as exc:
        logger.error("ATS: LLM eligibility check failed for candidate=%s job=%s: %s", candidate_id, job_posting_id, exc)
        raise

    return _score_ats_output(llm_result)
