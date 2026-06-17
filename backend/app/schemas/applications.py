from pydantic import BaseModel


class ApplyRequest(BaseModel):
    job_posting_id: str
    candidate_id: str


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


class InterviewStagesResponse(BaseModel):
    application_id: str
    rounds: list[InterviewRoundInfo]
    current_round_id: str | None  # interview_round_id of the active round
