from pydantic import BaseModel, Field


class QuestionItem(BaseModel):
    iq_id: str
    question_id: str = ""
    question_text: str
    question_type: str = "short_answer"  # "mcq" | "short_answer" | "scenario"
    options: list[str] | None = None      # MCQ choices only — never the correct answer
    candidate_answer: str | None = None
    score: float | None = None
    notes: str | None = None
    # Server-side only: never serialized in API responses (would leak the MCQ answer
    # to the candidate before they submit). Used internally by the scoring path.
    correct_option: str | None = Field(default=None, exclude=True)


class GenerateQuestionsRequest(BaseModel):
    return_questions: bool = True
    test_mode: bool = False


class GenerateQuestionsResponse(BaseModel):
    interview_id: str
    questions: list[QuestionItem]
    timer_seconds: int
    interview_type: str = ""
    enable_fail_cases: bool = True


class AnswerItem(BaseModel):
    iq_id: str
    candidate_answer: str


class SaveAnswerRequest(BaseModel):
    iq_id: str
    candidate_answer: str


class ScoreAnswersRequest(BaseModel):
    fetch_from_db: bool = False
    answers: list[AnswerItem] = []
    test_mode: bool = False
    # timer_end | submit | normal_completion — tells the validator what triggered scoring
    event_type: str = "submit"
    interview_type: str = "written"


class GradedAnswer(BaseModel):
    question_text: str
    candidate_answer: str
    score: int
    notes: str
    is_correct: bool = False  # derived: score >= 7


class ScoreAnswersResponse(BaseModel):
    overall_score: float
    total_graded: int
    graded_answers: list[GradedAnswer]
    result: str  # "Pass" or "Failed" — the final result; already computed against
                 # passing_threshold by interview_validator, not recomputed client-side
    improvement_recommendations: str = ""
    # Written-test pass/fail summary (see interview_validator.WRITTEN_TEST_MIN_CORRECT).
    # Populated for every scoring call; only meaningful to display for non-oral rounds.
    total_questions: int = 0
    passed_questions: int = 0
    passing_threshold: int = 0
