import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.jobs import (
    VALID_JOB_TYPES,
    CandidatePanelResponse,
    DeleteInterviewResponse,
    EvaluationQuestionItem,
    InterviewRoundTypeItem,
    JobInterviewRoundItem,
    JobListItem,
    JobPostRequest,
    JobPostResponse,
    JobSkillOptionItem,
    JobStatsResponse,
    JobUpdateRequest,
    RerunAtsResponse,
    RerunAtsStatusResponse,
    RoundCandidateItem,
)
from app.services import interview_service, scheduling_service
from app.services.events import publish_job_update
from app.services.google_calendar_service import cancel_event
from app.services.interview_service import InterviewNotDeletableError
from app.services.job_service import (
    get_ats_rerun_status,
    get_candidate_panel,
    get_interview_qa,
    get_job_required_skills,
    get_job_rounds,
    get_job_stats,
    get_round_candidates,
    list_interview_round_types,
    list_jobs,
    list_recruiter_jobs,
    post_job,
    rerun_ats_for_job,
    update_job,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Literal routes first — never shadowed by /{job_id}/... ──────────────────

@router.get("/interview-qa/{interview_id}", response_model=list[EvaluationQuestionItem])
def get_qa_for_interview(interview_id: str) -> list[EvaluationQuestionItem]:
    try:
        return get_interview_qa(interview_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/round-types", response_model=list[InterviewRoundTypeItem])
def get_interview_round_types() -> list[InterviewRoundTypeItem]:
    try:
        return list_interview_round_types()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/interviews/{interview_id}", response_model=DeleteInterviewResponse)
def delete_scheduled_interview(interview_id: str, recruiter_id: str = Query(...)) -> DeleteInterviewResponse:
    """Recruiter-initiated cancel of a scheduled-but-not-yet-started interview round —
    the Job Stats page's "Delete" action next to a scheduled candidate. Mirrors the
    webhook's own cancelled-event handling (_handle_cancelled_event in
    google_calendar.py): revoke the pending Celery ETA task, best-effort remove the
    Calendar event, then clear the Interviews row's schedule (it is NOT deleted — see
    interview_service.delete_interview_round)."""
    ctx = interview_service.get_schedule_context(interview_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Interview {interview_id} not found")
    if ctx["recruiter_id"] != recruiter_id:
        raise HTTPException(status_code=403, detail="You don't own this interview's job posting")

    try:
        scheduling_service.revoke_pending_schedule_task(ctx["schedule_task_id"])
        if ctx["google_event_id"]:
            cancel_event(recruiter_id, ctx["google_event_id"])
        interview_service.delete_interview_round(interview_id)
    except InterviewNotDeletableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        asyncio.run(publish_job_update(
            ctx["job_posting_id"],
            {"event": "interview_unscheduled", "interview_id": interview_id},
        ))
    except Exception:
        logger.exception("jobs: failed to publish interview_unscheduled job_update for job_id=%s", ctx["job_posting_id"])

    return DeleteInterviewResponse(status="deleted", interview_id=interview_id)


@router.get("/mine", response_model=list[JobListItem])
def get_recruiter_jobs(recruiter_id: str) -> list[JobListItem]:
    try:
        return list_recruiter_jobs(recruiter_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("", response_model=list[JobListItem])
def get_jobs(
    job_role_id: Optional[int] = Query(None, ge=1, description="Filter by job role ID"),
    experience_level_id: Optional[int] = Query(None, ge=1, description="Filter by experience level ID"),
    location: Optional[str] = Query(None, description="Filter by location (partial match)"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    salary_range: Optional[str] = Query(None, description="Filter by salary range keyword"),
    candidate_id: Optional[str] = Query(None, description="When provided, exclude jobs the candidate has already applied to"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Pagination page size"),
) -> list[JobListItem]:
    if job_type and job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"job_type must be one of: {', '.join(VALID_JOB_TYPES)}",
        )
    try:
        return list_jobs(
            job_role_id=job_role_id,
            experience_level_id=experience_level_id,
            location=location,
            job_type=job_type,
            salary_range=salary_range,
            candidate_id=candidate_id,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", response_model=JobPostResponse)
def create_job(body: JobPostRequest) -> JobPostResponse:
    try:
        return post_job(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Parameterised routes last ────────────────────────────────────────────────

@router.get("/{job_id}/rounds", response_model=list[JobInterviewRoundItem])
def get_rounds_for_job(job_id: str) -> list[JobInterviewRoundItem]:
    try:
        return get_job_rounds(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}/stats", response_model=JobStatsResponse)
def get_stats_for_job(job_id: str) -> JobStatsResponse:
    try:
        return get_job_stats(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}/skills", response_model=list[JobSkillOptionItem])
def get_skills_for_job(job_id: str) -> list[JobSkillOptionItem]:
    try:
        return get_job_required_skills(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{job_id}", response_model=JobPostResponse)
def edit_job(job_id: str, body: JobUpdateRequest, recruiter_id: str = Query(...)) -> JobPostResponse:
    try:
        return update_job(job_id, recruiter_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{job_id}/rerun-ats", response_model=RerunAtsResponse)
def rerun_ats(job_id: str, recruiter_id: str = Query(...)) -> RerunAtsResponse:
    try:
        return rerun_ats_for_job(job_id, recruiter_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}/rerun-ats/status", response_model=RerunAtsStatusResponse)
def rerun_ats_status(job_id: str) -> RerunAtsStatusResponse:
    try:
        return get_ats_rerun_status(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}/rounds/{round_order}/candidates", response_model=list[RoundCandidateItem])
def get_candidates_for_round(job_id: str, round_order: int) -> list[RoundCandidateItem]:
    try:
        return get_round_candidates(job_id, round_order)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}/candidate-panel/{application_id}", response_model=CandidatePanelResponse)
def get_candidate_panel_endpoint(
    job_id: str,  # noqa: ARG001 — kept for REST path consistency
    application_id: str,
    interview_id: str,
) -> CandidatePanelResponse:
    try:
        return get_candidate_panel(application_id, interview_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
