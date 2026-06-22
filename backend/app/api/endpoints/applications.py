from fastapi import APIRouter, HTTPException, Query

from app.schemas.applications import (
    ATSCheckResponse,
    ApplyRequest,
    ApplyResponse,
    InterviewStagesResponse,
)
from app.services.application_service import apply_to_job, get_interview_stages

router = APIRouter()


@router.post("/apply", response_model=ApplyResponse)
def apply(body: ApplyRequest) -> ApplyResponse:
    try:
        return apply_to_job(body.job_posting_id, body.candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ats-check", response_model=ATSCheckResponse)
async def ats_check(
    job_posting_id: str = Query(...),
    candidate_id: str = Query(...),
) -> ATSCheckResponse:
    from app.ai.ai_services.ats_service import check_ats_eligibility

    try:
        result = await check_ats_eligibility(candidate_id, job_posting_id)
        return ATSCheckResponse(eligible=result.eligible, reason=result.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{application_id}/interview-stages", response_model=InterviewStagesResponse)
def interview_stages(application_id: str) -> InterviewStagesResponse:
    try:
        return get_interview_stages(application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
