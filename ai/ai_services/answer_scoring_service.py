from agents.interview_agent.prompts import GRADE_ANSWERS_SYSTEM_PROMPT
from agents.interview_agent.schemas import AnswerItem, GradedAnswers
from ai_configs.config import get_llm


async def grade_candidate_answers(answers: list[AnswerItem]) -> GradedAnswers:
    """grade_candidate_answers(): LLM call scoring each candidate answer and
    computing the overall score."""

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
