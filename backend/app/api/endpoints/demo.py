from fastapi import APIRouter

from app.schemas.schema import DemoMessage
from app.services.demo_service import get_demo_message

router = APIRouter()


@router.get("/", response_model=DemoMessage)
def read_demo() -> DemoMessage:
    return get_demo_message()
