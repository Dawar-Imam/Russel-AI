from typing import Literal

from pydantic import BaseModel, Field, field_validator

VALID_JOB_TYPES = ('Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid')


class InterviewRoundTypeItem(BaseModel):
    id: int
    name: str
    description: str | None


class InterviewRoundInput(BaseModel):
    round_type_id: int
    round_order: int
    failing_criteria: int | None = None  # 0–100 percent
    description: str | None = None
    time_limit_minutes: int | None = None  # written-test time limit; falls back to a global default when unset

    @field_validator('failing_criteria')
    @classmethod
    def validate_failing_criteria(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError('failing_criteria must be between 0 and 100')
        return v

    @field_validator('time_limit_minutes')
    @classmethod
    def validate_time_limit_minutes(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError('time_limit_minutes must be positive')
        return v


class ATSCriterionInput(BaseModel):
    section: Literal['experience', 'skills', 'projects', 'certifications', 'education', 'achievements']
    weight: float = Field(ge=0, le=100)


class JobPostRequest(BaseModel):
    recruiter_id: str
    job_role_id: int
    experience_level_id: int
    description: str
    location: str
    job_type: Literal['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']
    salary_range: str | None = None
    expires_at: str | None = None
    skill_ids: list[int] = []
    interview_rounds: list[InterviewRoundInput] = []
    ats_criteria: list[ATSCriterionInput] = Field(..., min_length=1)
    # Axis 1 (PASS/FAIL) — weighted_average vs this threshold. Defaults to 65 when not set by the
    # recruiter, rather than being required, so the form doesn't force every recruiter to think
    # about it.
    qualify_threshold: float = Field(65, ge=0, le=100)
    # Axis 2 (overqualification flag) — independent of qualify_threshold. None means
    # overqualification is never auto-rejected, only shown informationally.
    overqualify_threshold: float | None = Field(None, ge=0)
    auto_reject_overqualified: bool = False

    @field_validator('description', 'location', 'recruiter_id')
    @classmethod
    def validate_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('This field is required')
        return v

    @field_validator('ats_criteria')
    @classmethod
    def validate_ats_criteria(cls, v: list[ATSCriterionInput]) -> list[ATSCriterionInput]:
        if abs(sum(c.weight for c in v) - 100) > 1e-6:
            raise ValueError('ats_criteria weights must sum to 100')
        return v

    @field_validator('salary_range')
    @classmethod
    def validate_salary_range(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class JobUpdateRequest(BaseModel):
    """Recruiter edit of an already-posted job. Deliberately excludes `interview_rounds` —
    rounds are locked once a job is live (candidates may already have Interviews rows tied
    to them); everything else is editable."""
    description: str | None = None
    location: str | None = None
    job_type: Literal['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid'] | None = None
    salary_range: str | None = None
    expires_at: str | None = None
    status: Literal['active', 'closed'] | None = None
    skill_ids: list[int] | None = None
    ats_criteria: list[ATSCriterionInput] | None = None
    qualify_threshold: float | None = Field(None, ge=0, le=100)
    overqualify_threshold: float | None = Field(None, ge=0)
    auto_reject_overqualified: bool | None = None

    @field_validator('ats_criteria')
    @classmethod
    def validate_ats_criteria(cls, v: list[ATSCriterionInput] | None) -> list[ATSCriterionInput] | None:
        if v is not None and abs(sum(c.weight for c in v) - 100) > 1e-6:
            raise ValueError('ats_criteria weights must sum to 100')
        return v


class JobPostResponse(BaseModel):
    job_id: str
    message: str


class JobSkillOptionItem(BaseModel):
    """A job's currently-required skill, with its id — unlike JobListItem.required_skills
    (a flat list of names via STRING_AGG), this is what the recruiter-edit skill picker
    needs to pre-fill selections and submit skill_ids back to PUT /jobs/{job_id}."""
    id: int
    name: str


class RerunAtsResponse(BaseModel):
    queued: int
    skipped_pending: int
    excluded: int
    in_progress_count: int
    not_stale_count: int
    message: str


class RerunAtsStatusResponse(BaseModel):
    """Polled by the recruiter dashboard while a rerun batch is in flight — `pending`
    is derived from how many of the applications queued by the most recent rerun still
    have an ats_evaluated_at older than when the batch was dispatched."""
    total_queued: int
    completed: int
    in_progress: bool


class JobInterviewRoundItem(BaseModel):
    round_order: int
    round_type_name: str
    failing_criteria: int | None
    description: str | None
    time_limit_minutes: int | None


class ATSCriterionSummary(BaseModel):
    section: str
    weight: float


class ATSCriteriaSummary(BaseModel):
    """Read-only, normalized view of a job's ats_criteria for display (e.g. the
    recruiter dashboard's job detail dialog). has_config=False means the job predates
    recruiter-defined ATS weighting (or the stored JSON was malformed) and the
    hardcoded default category weights are in effect instead of `criteria`.
    """

    has_config: bool
    criteria: list[ATSCriterionSummary]
    qualify_threshold: float
    overqualify_threshold: float | None
    auto_reject_overqualified: bool


class JobListItem(BaseModel):
    id: str
    description: str
    company: str
    job_role_id: int
    job_role_title: str
    experience_level_id: int
    experience_level_name: str
    location: str
    job_type: str
    salary_range: str | None
    posted_at: str
    expires_at: str | None
    required_skills: list[str]
    status: str = 'active'
    # Only populated for recruiter-facing listings (list_recruiter_jobs) — omitted (None)
    # from the public/candidate job list so scoring thresholds aren't exposed to candidates.
    ats_criteria: ATSCriteriaSummary | None = None


# ── Job analytics schemas ─────────────────────────────────────────────────────

class JobStatsRound(BaseModel):
    round_order: int
    round_type_name: str
    failing_criteria: int | None
    applicants_count: int


class JobStatsResponse(BaseModel):
    job_title: str
    description: str
    status: str
    required_skills: list[str]
    rounds: list[JobStatsRound]
    total_applicants: int
    passed_all_rounds: int
    hired_count: int


class RoundCandidateItem(BaseModel):
    candidate_id: str
    application_id: str
    interview_id: str
    name: str
    status: str


class CandidateSkillItem(BaseModel):
    name: str
    proficiency_level: str | None


class CandidateInfo(BaseModel):
    first_name: str
    last_name: str
    email: str
    bio: str | None
    current_location: str | None
    experience_level: str | None
    job_role: str | None
    skills: list[CandidateSkillItem]
    phone: str | None
    linkedin_url: str | None
    experience_years_min: int | None
    experience_years_max: int | None


class InterviewProgressItem(BaseModel):
    round_order: int
    round_type_name: str
    status: str | None
    result: float | None
    completed_at: str | None
    interview_id: str | None


class EvaluationQuestionItem(BaseModel):
    question_text: str
    candidate_answer: str | None
    score: int | None
    notes: str | None


class CandidatePanelResponse(BaseModel):
    candidate: CandidateInfo
    progress: list[InterviewProgressItem]
    evaluation: list[EvaluationQuestionItem] | None
