import uuid

from app.ai.interview_tools.schemas import AnswerItem as AIAnswerItem
from app.ai.interview_tools.state import AgentState
from app.ai.interview_tools.tools import generate_questions_tool, score_answers_tool
from app.database import get_connection
from app.schemas.interviews import (
    AnswerItem,
    GenerateQuestionsResponse,
    GradedAnswer,
    QuestionItem,
    ScoreAnswersResponse,
)

TIMER_SECONDS = 300
PASS_THRESHOLD = 6.0


# ---------------------------------------------------------------------------
# Context fetcher
# ---------------------------------------------------------------------------

def get_interview_context(interview_id: str) -> dict:
    """Fetch all context needed for question generation from the interview record."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                i.application_id,
                a.job_id              AS job_posting_id,
                ir.interview_round_type_id,
                jp.job_role_id,
                a.candidate_id,
                irt.name              AS interview_type
            FROM Interviews i
            JOIN Applications a          ON a.id   = i.application_id
            JOIN InterviewRounds ir      ON ir.id  = i.interview_round_id
            JOIN JobPostings jp          ON jp.id  = a.job_id
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            WHERE i.id = ?
            """,
            interview_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Interview {interview_id} not found")
        return {
            "application_id": str(row[0]),
            "job_posting_id": str(row[1]),
            "interview_round_type_id": int(row[2]),
            "job_role_id": int(row[3]),
            "candidate_id": str(row[4]),
            "interview_type": str(row[5]) if row[5] else "",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _fetch_existing_questions(cur, interview_id: str) -> list[QuestionItem]:
    """Return questions for this interview with complete data from both tables."""
    cur.execute(
        """
        SELECT iq.id, iq.question_id, q.question_text, iq.candidate_answer, iq.score, iq.notes
        FROM InterviewQuestions iq
        JOIN Questions q ON q.id = iq.question_id
        WHERE iq.interview_id = ?
        ORDER BY iq.id
        """,
        interview_id,
    )
    return [
        QuestionItem(
            iq_id=str(r[0]),
            question_id=str(r[1]),
            question_text=r[2],
            candidate_answer=r[3],
            score=float(r[4]) if r[4] is not None else None,
            notes=r[5],
        )
        for r in cur.fetchall()
    ]


def _store_generated_questions(
    cur,
    interview_id: str,
    question_texts: list[str],
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
) -> list[QuestionItem]:
    """Insert into Questions + InterviewQuestions; return items with full data."""
    items: list[QuestionItem] = []
    for q_text in question_texts:
        q_id = str(uuid.uuid4())
        iq_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO Questions
                (id, interview_round_type_id, job_role_id, experience_level_id,
                 question_text, is_active, ai_generated, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 1, GETDATE())
            """,
            q_id, interview_round_type_id, job_role_id, experience_level_id, q_text,
        )
        cur.execute(
            """
            INSERT INTO InterviewQuestions
                (id, interview_id, question_id, candidate_answer, score, notes)
            VALUES (?, ?, ?, NULL, NULL, NULL)
            """,
            iq_id, interview_id, q_id,
        )
        items.append(QuestionItem(
            iq_id=iq_id,
            question_id=q_id,
            question_text=q_text,
            candidate_answer=None,
            score=None,
            notes=None,
        ))
    return items


def _save_candidate_answers(cur, interview_id: str, answers: list[AnswerItem]) -> None:
    for a in answers:
        cur.execute(
            """
            UPDATE InterviewQuestions
            SET candidate_answer = ?
            WHERE id = ? AND interview_id = ?
            """,
            a.candidate_answer, a.iq_id, interview_id,
        )


def _save_scores_and_complete(
    cur,
    interview_id: str,
    iq_ids: list[str],
    graded_answers,
    overall_score: float,
    interview_result: str,
) -> None:
    for iq_id, ga in zip(iq_ids, graded_answers):
        cur.execute(
            """
            UPDATE InterviewQuestions
            SET score = ?, notes = ?
            WHERE id = ? AND interview_id = ?
            """,
            ga.score, ga.notes, iq_id, interview_id,
        )
    cur.execute(
        """
        UPDATE Interviews
        SET status = 'Completed', result = ?, feedback = ?, completed_at = GETDATE()
        WHERE id = ?
        """,
        interview_result, str(overall_score), interview_id,
    )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def get_interview_questions(interview_id: str) -> list[QuestionItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        return _fetch_existing_questions(cur, interview_id)
    finally:
        conn.close()


def save_voice_answers_bulk(interview_id: str, answers: list[tuple[str, str]]) -> None:
    """Persist voice answers in one transaction. answers = [(iq_id, answer_text), ...]"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        for iq_id, answer_text in answers:
            cur.execute(
                "UPDATE InterviewQuestions SET candidate_answer = ? WHERE id = ? AND interview_id = ?",
                answer_text, iq_id, interview_id,
            )
        conn.commit()
    finally:
        conn.close()


async def generate_interview_questions(
    interview_id: str,
    return_questions: bool = True,
) -> GenerateQuestionsResponse:
    # --- 1. Fetch interview context ---
    ctx = get_interview_context(interview_id)
    interview_type = ctx["interview_type"]
    candidate_id = ctx["candidate_id"]
    job_posting_id = ctx["job_posting_id"]
    application_id = ctx["application_id"]
    interview_round_type_id = ctx["interview_round_type_id"]
    job_role_id = ctx["job_role_id"]

    # --- 2. Return early if questions already exist ---
    conn = get_connection()
    try:
        cur = conn.cursor()
        existing = _fetch_existing_questions(cur, interview_id)
        if existing:
            return GenerateQuestionsResponse(
                interview_id=interview_id,
                questions=existing if return_questions else [],
                timer_seconds=TIMER_SECONDS,
                interview_type=interview_type,
            )
        cur.execute(
            "SELECT experience_level_id FROM CandidateProfiles WHERE id = ?",
            candidate_id,
        )
        cp_row = cur.fetchone()
        experience_level_id = int(cp_row[0]) if cp_row and cp_row[0] else 1
    finally:
        conn.close()

    # --- 3. Generate questions via AI (no DB connection held during this) ---
    state: AgentState = {
        "candidate_id": candidate_id,
        "job_posting_id": job_posting_id,
        "application_id": application_id,
        "interview_round_type_id": interview_round_type_id,
        "job_role_id": job_role_id,
        "experience_level_id": experience_level_id,
        "count": 10,
    }
    result = await generate_questions_tool(state)
    if result["status"] != "success":
        raise RuntimeError("AI question generation failed")

    # --- 4. Persist questions and mark interview as In Progress ---
    conn = get_connection()
    try:
        cur = conn.cursor()
        items = _store_generated_questions(
            cur,
            interview_id,
            [q.question_text for q in result["questions"]],
            interview_round_type_id,
            job_role_id,
            experience_level_id,
        )
        cur.execute(
            "UPDATE Interviews SET status = 'In Progress' WHERE id = ?",
            interview_id,
        )
        conn.commit()
    finally:
        conn.close()

    return GenerateQuestionsResponse(
        interview_id=interview_id,
        questions=items if return_questions else [],
        timer_seconds=TIMER_SECONDS,
        interview_type=interview_type,
    )


async def score_interview_answers(
    interview_id: str,
    fetch_from_db: bool,
    answers: list[AnswerItem],
) -> ScoreAnswersResponse:
    if not fetch_from_db and not answers:
        raise ValueError("No answers submitted and fetch_from_db is False")

    # --- 1. Fetch questions from DB and build list to score ---
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Guard: prevent re-scoring a completed interview
        cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
        status_row = cur.fetchone()
        if not status_row:
            raise ValueError(f"Interview {interview_id} not found")
        if str(status_row[0]).lower() == "completed":
            raise ValueError("This interview has already been completed and scored.")

        stored = _fetch_existing_questions(cur, interview_id)
        if not stored:
            raise ValueError(f"No questions found for interview {interview_id}")

        if fetch_from_db:
            to_score = stored
        else:
            _save_candidate_answers(cur, interview_id, answers)
            conn.commit()
            iq_map = {q.iq_id: q for q in stored}
            to_score = [
                QuestionItem(
                    iq_id=a.iq_id,
                    question_id=iq_map[a.iq_id].question_id if a.iq_id in iq_map else "",
                    question_text=iq_map[a.iq_id].question_text if a.iq_id in iq_map else a.iq_id,
                    candidate_answer=a.candidate_answer,
                    score=None,
                    notes=None,
                )
                for a in answers
            ]
    finally:
        conn.close()

    # --- 2. Score answers via AI (no DB connection held during this) ---
    ai_answers = [
        AIAnswerItem(
            question_text=item.question_text,
            candidate_answer=item.candidate_answer or "",
        )
        for item in to_score
    ]
    state: AgentState = {"answers": ai_answers}
    result = await score_answers_tool(state)
    if result["status"] != "success":
        raise RuntimeError("AI answer scoring failed")

    overall_score: float = result["overall_score"]
    interview_result = "Pass" if overall_score > PASS_THRESHOLD else "Fail"

    # --- 3. Persist scores and mark interview completed ---
    conn = get_connection()
    try:
        cur = conn.cursor()
        _save_scores_and_complete(
            cur, interview_id,
            [item.iq_id for item in to_score],
            result["graded_answers"],
            overall_score, interview_result,
        )
        conn.commit()
    finally:
        conn.close()

    return ScoreAnswersResponse(
        overall_score=overall_score,
        total_graded=result["total_graded"],
        graded_answers=[
            GradedAnswer(
                question_text=g.question_text,
                candidate_answer=g.candidate_answer,
                score=g.score,
                notes=g.notes,
            )
            for g in result["graded_answers"]
        ],
        result=interview_result,
    )
