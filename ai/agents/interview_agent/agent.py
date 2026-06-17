from agents.interview_agent.schemas import AnswerItem, GradedAnswers
from agents.interview_agent.state import AgentState
from agents.interview_agent.tools import generate_questions_tool, score_answers_tool, validate_tool


async def generate_questions(
    candidate_id: str,
    job_posting_id: str,
    application_id: str,
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    count: int = 10,
) -> list[str]:
    state: AgentState = {
        "candidate_id": candidate_id,
        "job_posting_id": job_posting_id,
        "application_id": application_id,
        "interview_round_type_id": interview_round_type_id,
        "job_role_id": job_role_id,
        "experience_level_id": experience_level_id,
        "count": count,
    }

    result = await generate_questions_tool(state)
    if result["status"] != "success":
        raise RuntimeError("generate_questions_tool failed")
    state.update(result)

    # validation = await validate_tool(state)
    # if validation["status"] != "success":
    #     raise RuntimeError("validate_tool failed")

    return [q.question_text for q in state["questions"]]


async def assign_scores(questions: list[str], answers: list[str]) -> GradedAnswers:
    state: AgentState = {
        "answers": [
            AnswerItem(question_text=q, candidate_answer=a)
            for q, a in zip(questions, answers)
        ]
    }

    result = await score_answers_tool(state)
    if result["status"] != "success":
        raise RuntimeError("score_answers_tool failed")

    return GradedAnswers(
        overall_score=result["overall_score"],
        total_graded=result["total_graded"],
        graded_answers=result["graded_answers"],
    )
