from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared types used directly by the AI service functions (question_generation_
# service.py, answer_scoring_service.py, cv_relevance_service.py) and their
# callers (interview_service.py, question_pregeneration_service.py) — these
# functions are called directly, not through a tool-wrapper layer.
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


class AnswerItem(BaseModel):
    question_text: str
    candidate_answer: str


class GradedAnswer(BaseModel):
    question_text: str
    candidate_answer: str
    score: int
    notes: str


class GradedAnswers(BaseModel):
    """grade_candidate_answers() OUTPUT."""

    overall_score: float
    total_graded: int
    graded_answers: list[GradedAnswer]
