from pydantic import BaseModel


class QuestionItem(BaseModel):
    iq_id: str
    question_id: str = ""
    question_text: str
    candidate_answer: str | None = None
    score: float | None = None
    notes: str | None = None


class GenerateQuestionsRequest(BaseModel):
    return_questions: bool = True


class GenerateQuestionsResponse(BaseModel):
    interview_id: str
    questions: list[QuestionItem]
    timer_seconds: int
    interview_type: str = ""
    enable_fail_cases: bool = True


class AnswerItem(BaseModel):
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


class ScoreAnswersResponse(BaseModel):
    overall_score: float
    total_graded: int
    graded_answers: list[GradedAnswer]
    result: str  # "Pass" or "Failed"
