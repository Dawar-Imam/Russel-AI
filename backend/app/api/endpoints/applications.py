from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas.applications import (
    ATSCheckResponse,
    ApplyResponse,
    InterviewQuestionItem,
    InterviewStagesResponse,
    MyApplicationItem,
)
from app.services.application_service import apply_to_job, get_interview_questions, get_interview_stages, get_my_applications, run_ats_for_application

router = APIRouter()

_MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/apply", response_model=ApplyResponse)
async def apply(
    job_posting_id: str = Form(...),
    candidate_id: str = Form(...),
    cv: UploadFile | None = File(None),
) -> ApplyResponse:
    cv_content: bytes | None = None
    cv_filename: str | None = None
    if cv and cv.filename:
        cv_content = await cv.read()
        if len(cv_content) > _MAX_CV_BYTES:
            raise HTTPException(status_code=413, detail="CV file must be smaller than 5 MB")
        cv_filename = cv.filename

    try:
        result = apply_to_job(job_posting_id, candidate_id, cv_content=cv_content, cv_filename=cv_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        await run_ats_for_application(result.application_id)
    except Exception:
        pass

    return result


@router.get("/ats-check", response_model=ATSCheckResponse)
async def ats_check(
    job_posting_id: str = Query(...),
    candidate_id: str = Query(...),
) -> ATSCheckResponse:
    from app.ai.ai_services.ats_service import check_ats_eligibility

    try:
        result = await check_ats_eligibility(candidate_id, job_posting_id)
        return ATSCheckResponse(**result.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/my-applications", response_model=list[MyApplicationItem])
def my_applications(candidate_id: str = Query(...)) -> list[MyApplicationItem]:
    try:
        return get_my_applications(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{application_id}/run-ats", response_model=ATSCheckResponse)
async def run_ats(application_id: str) -> ATSCheckResponse:
    try:
        return await run_ats_for_application(application_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.get("/{application_id}/interviews/{interview_id}/questions", response_model=list[InterviewQuestionItem])
def interview_questions(application_id: str, interview_id: str) -> list[InterviewQuestionItem]:  # noqa: ARG001
    try:
        return get_interview_questions(interview_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
