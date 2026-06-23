import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.auth import CandidateProfileResponse, RecruiterProfileResponse, RecruiterSigninResponse, RecruiterSignupRequest, RecruiterSignupResponse, SigninRequest, SigninResponse, SignupMetadataResponse, SignupResponse
from app.services.auth_service import get_candidate_profile, get_recruiter_profile, get_signup_metadata, signin_candidate, signin_recruiter, signup_candidate, signup_recruiter

router = APIRouter()

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("/signup-metadata", response_model=SignupMetadataResponse)
def signup_metadata() -> SignupMetadataResponse:
    try:
        return get_signup_metadata()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/signup", response_model=SignupResponse)
async def signup(
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    job_role_id: int = Form(...),
    skill_ids: str = Form(...),
    experience_years: float = Form(...),
    cv: UploadFile | None = File(None),
) -> SignupResponse:
    # Validate individual form fields before touching the service
    errors: list[str] = []
    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip().lower()
    if not first_name:
        errors.append("first_name is required")
    if not last_name:
        errors.append("last_name is required")
    if not _EMAIL_RE.match(email):
        errors.append("Invalid email address")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if experience_years < 0:
        errors.append("experience_years must be 0 or greater")
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    try:
        ids = [int(x.strip()) for x in skill_ids.split(",") if x.strip()]

        cv_content: bytes | None = None
        cv_filename: str | None = None
        if cv and cv.filename:
            cv_content = await cv.read()
            if len(cv_content) > _MAX_CV_BYTES:
                raise HTTPException(status_code=413, detail="CV file must be smaller than 5 MB")
            cv_filename = cv.filename

        return signup_candidate(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
            job_role_id=job_role_id,
            skill_ids=ids,
            experience_years=experience_years,
            cv_content=cv_content,
            cv_filename=cv_filename,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/signin", response_model=SigninResponse)
def signin(body: SigninRequest) -> SigninResponse:
    try:
        return signin_candidate(email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/recruiter/signup", response_model=RecruiterSignupResponse)
def recruiter_signup(body: RecruiterSignupRequest) -> RecruiterSignupResponse:
    try:
        return signup_recruiter(
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            password=body.password,
            company_name=body.company_name,
            designation=body.designation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/recruiter/signin", response_model=RecruiterSigninResponse)
def recruiter_signin(body: SigninRequest) -> RecruiterSigninResponse:
    try:
        return signin_recruiter(email=body.email, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/profile/candidate/{candidate_id}", response_model=CandidateProfileResponse)
def candidate_profile(candidate_id: str) -> CandidateProfileResponse:
    try:
        return get_candidate_profile(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/profile/recruiter/{recruiter_id}", response_model=RecruiterProfileResponse)
def recruiter_profile(recruiter_id: str) -> RecruiterProfileResponse:
    try:
        return get_recruiter_profile(recruiter_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
