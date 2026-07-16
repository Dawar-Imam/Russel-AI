from app.ai.interview_tools.prompts import GRADE_ANSWERS_SYSTEM_PROMPT
from app.ai.interview_tools.schemas import AnswerItem, GradedAnswers
from app.core.config import get_llm


async def grade_candidate_answers(
    answers: list[AnswerItem],
    interview_type: str = "written",
) -> GradedAnswers:
    """LLM call scoring each candidate answer and computing the overall score."""

    structured_llm = get_llm().with_structured_output(GradedAnswers)

    def _format_answer(answer: AnswerItem) -> str:
        lines = [f"Q: {answer.question_text}"]
        if answer.question_type == "mcq" and answer.correct_option:
            lines.append("Type: MCQ")
            lines.append(f"Correct option: {answer.correct_option}")
        lines.append(f"A: {answer.candidate_answer or '(no answer)'}")
        return "\n".join(lines)

    qa_block = "\n\n".join(_format_answer(answer) for answer in answers)

    is_oral = interview_type.lower() in ("oral", "voice")
    round_note = (
        "\nCURRENT ROUND TYPE: ORAL — apply the ORAL INTERVIEWS (STT-BASED) rules above."
        if is_oral
        else "\nCURRENT ROUND TYPE: NON-ORAL / TEXT — apply the NON-ORAL / TEXT INTERVIEWS rules above."
    )
    system_prompt = GRADE_ANSWERS_SYSTEM_PROMPT + round_note

    return await structured_llm.ainvoke(
        [
            ("system", system_prompt),
            ("user", qa_block),
        ]
    )
