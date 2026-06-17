from fastapi import APIRouter, HTTPException

from app.schemas.interviews import (
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    ScoreAnswersRequest,
    ScoreAnswersResponse,
)
from app.services.interview_service import (
    generate_interview_questions,
    score_interview_answers,
)

router = APIRouter()


@router.post("/{interview_id}/generate-questions", response_model=GenerateQuestionsResponse)
async def generate_questions(
    interview_id: str,
    body: GenerateQuestionsRequest,
) -> GenerateQuestionsResponse:
    try:
        return await generate_interview_questions(
            interview_id=interview_id,
            return_questions=body.return_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/score-answers", response_model=ScoreAnswersResponse)
async def score_answers(
    interview_id: str,
    body: ScoreAnswersRequest,
) -> ScoreAnswersResponse:
    try:
        return await score_interview_answers(
            interview_id=interview_id,
            fetch_from_db=body.fetch_from_db,
            answers=body.answers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
