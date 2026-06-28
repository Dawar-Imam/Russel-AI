from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.jobs import VALID_JOB_TYPES, InterviewRoundTypeItem, JobInterviewRoundItem, JobListItem, JobPostRequest, JobPostResponse
from app.services.job_service import get_job_rounds, list_interview_round_types, list_jobs, list_recruiter_jobs, post_job

router = APIRouter()


# Literal routes first so they are never shadowed by /{job_id}/rounds
@router.get("/round-types", response_model=list[InterviewRoundTypeItem])
def get_interview_round_types() -> list[InterviewRoundTypeItem]:
    try:
        return list_interview_round_types()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


# Parameterised routes last
@router.get("/{job_id}/rounds", response_model=list[JobInterviewRoundItem])
def get_rounds_for_job(job_id: str) -> list[JobInterviewRoundItem]:
    try:
        return get_job_rounds(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
