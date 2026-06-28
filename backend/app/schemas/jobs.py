from typing import Literal

from pydantic import BaseModel, field_validator

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

    @field_validator('failing_criteria')
    @classmethod
    def validate_failing_criteria(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError('failing_criteria must be between 0 and 100')
        return v


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

    @field_validator('description', 'location', 'recruiter_id')
    @classmethod
    def validate_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('This field is required')
        return v

    @field_validator('salary_range')
    @classmethod
    def validate_salary_range(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class JobPostResponse(BaseModel):
    job_id: str
    message: str


class JobInterviewRoundItem(BaseModel):
    round_order: int
    round_type_name: str
    failing_criteria: int | None
    description: str | None


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
