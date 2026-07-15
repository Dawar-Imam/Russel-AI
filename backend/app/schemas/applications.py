from typing import Literal

from pydantic import BaseModel

from app.ai.ai_services.ats_service import (
    ATSCategoryScore as _ATSCategoryScore,
    ATSWeightage as _ATSWeightage,
    GraceCredit as ATSGraceCredit,
    RelevantExperienceResult as ATSRelevantExperience,
    RequirementMatchResult as _RequirementMatchResult,
    ResponsibilityMatchResult as ATSResponsibilityMatchItem,
    SectionMatchResult as ATSSectionMatchItem,
)


class ApplyRequest(BaseModel):
    job_posting_id: str
    candidate_id: str


# ---------------------------------------------------------------------------
# ATS result — the field shapes below are owned by app.ai.ai_services.ats_service
# (the AI service that produces a fresh ATS result); these subclasses only relax
# a few fields to Optional/defaulted so _parse_ats_details() can degrade legacy or
# malformed stored `ats_details` JSON to a partial/None result instead of raising,
# without needing a second, hand-maintained copy of every field.
# ---------------------------------------------------------------------------


class ATSCategoryScore(_ATSCategoryScore):
    included: bool = True


class ATSWeightage(_ATSWeightage):
    experience: ATSCategoryScore
    skills: ATSCategoryScore
    projects: ATSCategoryScore
    certifications: ATSCategoryScore
    education: ATSCategoryScore
    achievements: ATSCategoryScore
    qualify_threshold: float = 65
    pass_fail: Literal["PASS", "FAIL"] | None = None


class ATSRequirementMatchItem(_RequirementMatchResult):
    category: Literal["skills", "projects", "certifications", "education", "achievements"] = "skills"
    max_score: float


class ATSCheckResponse(BaseModel):
    verdict: Literal["QUALIFIED", "UNDERQUALIFIED", "OVERQUALIFIED"]
    verdict_summary: str
    weightage: ATSWeightage | None = None
    requirement_matching: list[ATSRequirementMatchItem] = []
    relevant_experience: ATSRelevantExperience | None = None
    section_matching: list[ATSSectionMatchItem] = []
    grace_credits: list[ATSGraceCredit] = []
    additional_cv_content: list[str] = []
    is_overqualified: bool = False
    final_verdict: Literal["PASS", "FAIL"] | None = None
    override_reason: str | None = None


class ApplyResponse(BaseModel):
    application_id: str
    created: bool
    message: str


class InterviewRoundInfo(BaseModel):
    interview_round_id: str
    interview_id: str | None
    title: str
    round_order: int
    status: str | None
    feedback: str | None = None
    result: float | None = None
    scheduled_at: str | None = None
    completed_at: str | None = None
    avg_score: float | None = None


class InterviewStagesResponse(BaseModel):
    application_id: str
    rounds: list[InterviewRoundInfo]
    current_round_id: str | None  # interview_round_id of the active round
    ats_status: str  # 'pending' | 'pass' | 'fail'
    ats_result: ATSCheckResponse | None = None
    application_status: str | None = None  # raw DB value: ATS_PENDING/ATS_PASS/ATS_FAIL/IN_PROGRESS/HIRED/REJECTED
    job_role_title: str | None = None
    experience_level_name: str | None = None
    company: str | None = None


class InterviewQuestionItem(BaseModel):
    question_id: str
    question_text: str
    candidate_answer: str | None = None
    score: int | None = None
    notes: str | None = None


class MyApplicationItem(BaseModel):
    application_id: str
    job_id: str
    status: str
    applied_at: str
    description: str
    location: str | None
    job_type: str
    salary_range: str | None
    job_role_id: int
    job_role_title: str
    experience_level_id: int
    experience_level_name: str
    company: str
    latest_interview_round_title: str | None = None
