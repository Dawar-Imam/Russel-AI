from fastapi import APIRouter

from app.api.endpoints import applications, auth, demo, google_calendar, interviews, jobs

api_router = APIRouter()
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
api_router.include_router(auth.router, prefix="/api/auth", tags=["auth"])
api_router.include_router(applications.router, prefix="/api/applications", tags=["applications"])
api_router.include_router(interviews.router, prefix="/api/interviews", tags=["interviews"])
api_router.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
api_router.include_router(google_calendar.router, prefix="/api/google-calendar", tags=["google-calendar"])
