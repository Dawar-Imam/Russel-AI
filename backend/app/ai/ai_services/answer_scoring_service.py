from app.ai.interview_tools.prompts import GRADE_ANSWERS_ORAL_ADDENDUM, GRADE_ANSWERS_SYSTEM_PROMPT
from app.ai.interview_tools.schemas import AnswerItem, GradedAnswers
from app.core.config import get_llm


async def grade_candidate_answers(
    answers: list[AnswerItem],
    interview_type: str = "written",
) -> GradedAnswers:
    """LLM call scoring each candidate answer and computing the overall score."""

    structured_llm = get_llm().with_structured_output(GradedAnswers)

    qa_block = "\n\n".join(
        f"Q: {answer.question_text}\nA: {answer.candidate_answer or '(no answer)'}"
        for answer in answers
    )

    system_prompt = GRADE_ANSWERS_SYSTEM_PROMPT
    if interview_type.lower() in ("oral", "voice"):
        system_prompt += GRADE_ANSWERS_ORAL_ADDENDUM

    return await structured_llm.ainvoke(
        [
            ("system", system_prompt),
            ("user", qa_block),
        ]
    )
