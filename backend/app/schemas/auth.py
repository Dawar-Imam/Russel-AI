import re

from pydantic import BaseModel, field_validator

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class JobRoleItem(BaseModel):
    id: int
    title: str
    category: str | None = None


class SkillItem(BaseModel):
    id: int
    name: str
    category: str | None = None
    job_role_ids: list[int]


class ExperienceLevelItem(BaseModel):
    id: int
    name: str


class SignupMetadataResponse(BaseModel):
    job_roles: list[JobRoleItem]
    skills: list[SkillItem]
    experience_levels: list[ExperienceLevelItem]


class SignupResponse(BaseModel):
    user_id: str
    candidate_id: str
    message: str


class SigninRequest(BaseModel):
    email: str
    password: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError('Invalid email address')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError('Password is required')
        return v


class SigninResponse(BaseModel):
    user_id: str
    candidate_id: str
    message: str


class RecruiterSignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    company_name: str
    designation: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError('Invalid email address')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @field_validator('first_name', 'last_name', 'company_name', 'designation')
    @classmethod
    def validate_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('This field is required')
        return v


class RecruiterSignupResponse(BaseModel):
    user_id: str
    recruiter_id: str
    message: str


class RecruiterSigninResponse(BaseModel):
    user_id: str
    recruiter_id: str
    message: str


class CandidateProfileResponse(BaseModel):
    candidate_id: str
    first_name: str
    last_name: str
    email: str
    job_role_title: str
    skills: list[str]
    experience_level: str
    bio: str | None
    linkedin_url: str | None
    current_location: str | None
    open_to_work: bool
    resume_url: str | None
    member_since: str


class RecruiterProfileResponse(BaseModel):
    recruiter_id: str
    first_name: str
    last_name: str
    email: str
    company_name: str
    designation: str
    company_verified: bool
    member_since: str
