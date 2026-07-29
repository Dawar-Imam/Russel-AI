import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import ws
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.events import start_ats_completed_listener, start_job_update_listener

configure_logging()

app = FastAPI(title=settings.PROJECT_NAME)


@app.on_event("startup")
async def _start_ats_completed_listener() -> None:
    start_ats_completed_listener(asyncio.get_running_loop())
    start_job_update_listener(asyncio.get_running_loop())


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws.router)
# app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
