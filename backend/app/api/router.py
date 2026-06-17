from fastapi import APIRouter

from app.api.endpoints import applications, demo, interviews

api_router = APIRouter()
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
api_router.include_router(applications.router, prefix="/api/applications", tags=["applications"])
api_router.include_router(interviews.router, prefix="/api/interviews", tags=["interviews"])
