from app.ai.ai_services.answer_scoring_service import grade_candidate_answers
from app.ai.ai_services.cv_relevance_service import fetch_candidate_cv_relevance
from app.ai.ai_services.question_bank_service import fetch_interview_context, fetch_questions_from_db
from app.ai.ai_services.question_generation_service import generate_questions
from app.ai.interview_tools.schemas import CandidateCVRelevance
from app.ai.interview_tools.state import AgentState


async def generate_questions_tool(state: AgentState) -> dict:
    """fetch_questions_from_db + fetch_candidate_cv_relevance -> generate_questions."""

    try:
        count = state.get("count", 10)

        context = await fetch_interview_context(
            interview_round_type_id=state["interview_round_type_id"],
            job_role_id=state["job_role_id"],
            experience_level_id=state["experience_level_id"],
        )
        example_questions = await fetch_questions_from_db(
            interview_round_type_id=state["interview_round_type_id"],
            job_role_id=state["job_role_id"],
            experience_level_id=state["experience_level_id"],
        )
        parsed_cv_text = await fetch_candidate_cv_relevance(
            application_id=state["application_id"],
        )
        candidate_relevance = CandidateCVRelevance(
            job_experience_summary=parsed_cv_text,
            relevant_skills=[],
            relevant_projects=[],
        )

        generated = await generate_questions(
            example_questions=example_questions.questions,
            candidate_relevance=candidate_relevance,
            count=count,
            context=context,
        )

        return {
            "status": "success",
            "questions": generated.generated_questions,
            "total_questions": len(generated.generated_questions),
            "last_tool_used": "generate_questions_tool",
        }
    except Exception as e:
        print(f"Error in generate_questions_tool: {e}")
        return {"status": "error", "last_tool_used": "generate_questions_tool"}


async def validate_tool(state: AgentState) -> dict:
    """Validates generated questions or scores (stub — full implementation TBD)."""
    try:
        if not state.get("questions"):
            return {"status": "error", "last_tool_used": "validate_tool"}
        return {"status": "success", "last_tool_used": "validate_tool"}
    except Exception:
        return {"status": "error", "last_tool_used": "validate_tool"}


async def score_answers_tool(state: AgentState) -> dict:
    """grade_candidate_answers."""

    try:
        result = await grade_candidate_answers(state["answers"])

        return {
            "status": "success",
            "overall_score": result.overall_score,
            "total_graded": result.total_graded,
            "graded_answers": result.graded_answers,
            "last_tool_used": "score_answers_tool",
        }
    except Exception:
        return {"status": "error", "last_tool_used": "score_answers_tool"}
