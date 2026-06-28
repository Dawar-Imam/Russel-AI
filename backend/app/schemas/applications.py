from pydantic import BaseModel


class ApplyRequest(BaseModel):
    job_posting_id: str
    candidate_id: str


class ATSCheckResponse(BaseModel):
    eligible: bool
    reason: str


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
    ats_reason: str | None
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
