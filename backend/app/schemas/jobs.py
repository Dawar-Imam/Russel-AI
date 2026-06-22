from typing import Literal

from pydantic import BaseModel, field_validator

VALID_JOB_TYPES = ('Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid')


class JobPostRequest(BaseModel):
    recruiter_id: str
    job_role_id: int
    designation: str
    description: str
    location: str
    job_type: Literal['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']
    salary_range: str | None = None
    expires_at: str | None = None

    @field_validator('designation', 'description', 'location', 'recruiter_id')
    @classmethod
    def validate_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('This field is required')
        return v

    @field_validator('designation')
    @classmethod
    def validate_designation_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError('Designation must be 200 characters or fewer')
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


class JobListItem(BaseModel):
    id: str
    designation: str
    description: str
    company: str
    job_role_id: int
    job_role_title: str
    location: str
    job_type: str
    salary_range: str | None
    posted_at: str
    expires_at: str | None
    required_skills: list[str]
