from typing import Literal, TypedDict

from app.ai.interview_tools.schemas import AnswerItem, GradedAnswer, QuestionItem


class AgentState(TypedDict, total=False):
    """Interview Agent graph state (see .claude/agent-architecture.md)."""

    # --- shared agent state ---
    candidate_id: str
    job_posting_id: str
    application_id: str
    interview_round_type_id: int
    job_role_id: int
    experience_level_id: int
    last_tool_used: str
    status: Literal["success", "error"]

    # --- generate_questions_tool ---
    count: int
    use_example_questions: bool  # default False — when True, DB question bank is passed to LLM
    questions: list[QuestionItem]
    total_questions: int

    # --- score_answers_tool ---
    answers: list[AnswerItem]
    interview_type: str  # "written" | "oral" — oral answers get STT-hallucination leniency
    graded_answers: list[GradedAnswer]
    overall_score: float
    total_graded: int
