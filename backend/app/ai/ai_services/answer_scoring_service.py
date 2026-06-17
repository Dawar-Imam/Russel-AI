from app.ai.interview_tools.prompts import GRADE_ANSWERS_SYSTEM_PROMPT
from app.ai.interview_tools.schemas import AnswerItem, GradedAnswers
from app.core.config import get_llm


async def grade_candidate_answers(answers: list[AnswerItem]) -> GradedAnswers:
    """LLM call scoring each candidate answer and computing the overall score."""

    structured_llm = get_llm().with_structured_output(GradedAnswers)

    qa_block = "\n\n".join(
        f"Q: {answer.question_text}\nA: {answer.candidate_answer or '(no answer)'}"
        for answer in answers
    )

    return await structured_llm.ainvoke(
        [
            ("system", GRADE_ANSWERS_SYSTEM_PROMPT),
            ("user", qa_block),
        ]
    )
