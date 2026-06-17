from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class QuestionItem(BaseModel):
    question_text: str


class RelevantSkill(BaseModel):
    skill_name: str
    proficiency_level: str
    years_of_experience: int


class RelevantProject(BaseModel):
    project_name: str
    description: str
    skills_used: list[str]


# ---------------------------------------------------------------------------
# 1. generate_questions_tool
# ---------------------------------------------------------------------------
class GenerateQuestionsToolInput(BaseModel):
    """generate_questions_tool INPUT (everything else comes from AgentState)."""

    count: int = 10


class FetchQuestionsFromDBOutput(BaseModel):
    """fetch_questions_from_db() OUTPUT."""

    questions: list[QuestionItem]


class CandidateCVRelevance(BaseModel):
    """fetch_candidate_cv_relevance() OUTPUT."""

    job_experience_summary: str
    relevant_skills: list[RelevantSkill]
    relevant_projects: list[RelevantProject]


class GeneratedQuestions(BaseModel):
    """generate_questions() OUTPUT."""

    generated_questions: list[QuestionItem]


class GenerateQuestionsToolOutput(BaseModel):
    """generate_questions_tool FINAL OUTPUT."""

    status: Literal["success", "error"]
    total_questions: int
    questions: list[QuestionItem]


# ---------------------------------------------------------------------------
# 2. score_answers_tool
# ---------------------------------------------------------------------------
class AnswerItem(BaseModel):
    question_text: str
    candidate_answer: str


class ScoreAnswersToolInput(BaseModel):
    """score_answers_tool INPUT."""

    answers: list[AnswerItem]


class GradedAnswer(BaseModel):
    question_text: str
    candidate_answer: str
    score: int
    notes: str


class GradedAnswers(BaseModel):
    """grade_candidate_answers() result, before the tool attaches `status`."""

    overall_score: float
    total_graded: int
    graded_answers: list[GradedAnswer]


class ScoreAnswersToolOutput(BaseModel):
    """score_answers_tool OUTPUT."""

    status: Literal["success", "error"]
    overall_score: float
    total_graded: int
    graded_answers: list[GradedAnswer]
