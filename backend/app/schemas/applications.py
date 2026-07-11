from typing import Literal

from pydantic import BaseModel


class ApplyRequest(BaseModel):
    job_posting_id: str
    candidate_id: str


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
    pass_threshold: int


class ATSSeniorityMatch(BaseModel):
    required: str
    candidate: str
    status: Literal["match", "underqualified", "overqualified"]
    note: str


class ATSYearsMatch(BaseModel):
    required_years: float | None = None
    candidate_years: float | None = None


class ATSSkillMatchItem(BaseModel):
    requirement: str
    tier: Literal["primary", "secondary", "tertiary"]
    candidate_skill: str | None = None
    match_type: Literal["exact", "alternative", "not_found"]
    score: float
    max_score: float
    note: str


class ATSResponsibilityMatchItem(BaseModel):
    requirement: str
    evidence: str | None = None
    match_type: Literal["direct", "close", "not_found"]
    score: float


class ATSExperienceMatching(BaseModel):
    seniority: ATSSeniorityMatch
    years: ATSYearsMatch
    responsibilities: list[ATSResponsibilityMatchItem] = []


class ATSProjectMatchItem(BaseModel):
    project_name: str
    complexity: float
    technologies: float
    impact: float
    relevance: float
    total: float
    max: float = 4.0
    note: str


class ATSCertificationMatchItem(BaseModel):
    certification: str
    matches_requirement: bool
    recognition: Literal["industry_recognized", "not_recognized"]
    score: float


class ATSEducationMatching(BaseModel):
    relevant: bool
    score: float
    note: str


class ATSAchievementMatchItem(BaseModel):
    achievement: str
    relevant: bool
    required: bool
    score: float


class ATSCheckResponse(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    verdict_summary: str
    weightage: ATSWeightage | None = None
    skill_matching: list[ATSSkillMatchItem] = []
    experience_matching: ATSExperienceMatching | None = None
    projects_matching: list[ATSProjectMatchItem] = []
    certifications_matching: list[ATSCertificationMatchItem] = []
    education_matching: ATSEducationMatching | None = None
    achievements_matching: list[ATSAchievementMatchItem] = []
    additional_skills: list[str] = []


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
