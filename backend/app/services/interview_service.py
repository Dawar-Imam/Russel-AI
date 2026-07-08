import uuid

from app.ai.interview_tools.schemas import AnswerItem as AIAnswerItem
from app.ai.interview_tools.state import AgentState
from app.ai.interview_tools.tools import generate_questions_tool, score_answers_tool
from app.core.config import settings
from app.database import get_connection
from app.schemas.interviews import (
    AnswerItem,
    GenerateQuestionsResponse,
    GradedAnswer,
    QuestionItem,
    ScoreAnswersResponse,
)
from app.services.interview_validator import ValidationInput, validate_interview

TIMER_SECONDS = settings.INTERVIEW_DURATION_MINUTES * 60
PASS_THRESHOLD = 6.0

LEAVE_FEEDBACK = "User left the interview, interview automatically closed."

# ---------------------------------------------------------------------------
# Test-mode question cache
# ---------------------------------------------------------------------------
# test_mode interviews must never write Questions/InterviewQuestions rows to
# the DB. Generated questions (and, for voice interviews, extracted answers)
# are kept here in-memory, keyed by interview_id, and read back directly by
# scoring / the voice agent — no DB round-trip, so nothing can drift out of
# sync between what the candidate saw and what gets scored.
_test_mode_questions: dict[str, list[QuestionItem]] = {}


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


def _update_generated_questions(
    cur,
    interview_id: str,
    existing: list[QuestionItem],
    new_texts: list[str],
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
) -> list[QuestionItem]:
    """UPDATE Questions.question_text in-place, paired by position with new_texts.

    If the freshly generated count differs from `existing` (e.g. a regenerate
    that produces more/fewer questions than a prior attempt), surplus old rows
    are deleted and/or extra rows are inserted — the InterviewQuestions set
    always exactly matches the new generation, so no stale leftover question
    from a previous attempt can ever resurface alongside the new ones.
    """
    paired = min(len(existing), len(new_texts))
    updated: list[QuestionItem] = []
    for item, new_text in zip(existing[:paired], new_texts[:paired]):
        cur.execute(
            "UPDATE Questions SET question_text = ? WHERE id = ?",
            new_text, item.question_id,
        )
        updated.append(QuestionItem(
            iq_id=item.iq_id,
            question_id=item.question_id,
            question_text=new_text,
            candidate_answer=item.candidate_answer,
            score=item.score,
            notes=item.notes,
        ))

    for stale in existing[paired:]:
        cur.execute("DELETE FROM InterviewQuestions WHERE id = ?", stale.iq_id)
        cur.execute("DELETE FROM Questions WHERE id = ?", stale.question_id)

    extra_texts = new_texts[paired:]
    if extra_texts:
        updated.extend(_store_generated_questions(
            cur, interview_id, extra_texts,
            interview_round_type_id, job_role_id, experience_level_id,
        ))

    return updated


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


def _mark_subsequent_rounds_not_needed(cur, interview_id: str) -> None:
    """When a round is Failed, mark later still-Scheduled rounds of the same
    application as 'Not Needed' so the candidate doesn't appear to progress."""
    cur.execute(
        """
        UPDATE Interviews
        SET status = 'Not Needed'
        WHERE application_id = (SELECT application_id FROM Interviews WHERE id = ?)
          AND status = 'Scheduled'
          AND interview_round_id IN (
              SELECT id FROM InterviewRounds
              WHERE job_posting_id = (
                  SELECT job_posting_id FROM InterviewRounds
                  WHERE id = (SELECT interview_round_id FROM Interviews WHERE id = ?)
              )
              AND round_order > (
                  SELECT round_order FROM InterviewRounds
                  WHERE id = (SELECT interview_round_id FROM Interviews WHERE id = ?)
              )
          )
        """,
        interview_id, interview_id, interview_id,
    )


def _maybe_mark_hired(cur, interview_id: str) -> None:
    """When a round is Passed and no later active round exists for this job,
    the candidate has cleared every round — mark their application HIRED."""
    cur.execute(
        """
        UPDATE Applications
        SET status = 'HIRED'
        WHERE id = (SELECT application_id FROM Interviews WHERE id = ?)
          AND NOT EXISTS (
              SELECT 1 FROM InterviewRounds ir
              WHERE ir.job_posting_id = (
                  SELECT job_posting_id FROM InterviewRounds
                  WHERE id = (SELECT interview_round_id FROM Interviews WHERE id = ?)
              )
              AND ir.is_active = 1
              AND ir.round_order > (
                  SELECT round_order FROM InterviewRounds
                  WHERE id = (SELECT interview_round_id FROM Interviews WHERE id = ?)
              )
          )
        """,
        interview_id, interview_id, interview_id,
    )


def _save_question_scores(cur, iq_ids: list[str], graded_answers) -> None:
    """Persist per-question AI scores/notes only — used when the interview's
    final status/feedback is already locked in (e.g. the voice agent already
    concluded it as passed/failed) and must not be overwritten by a later
    display-only scoring pass."""
    for iq_id, ga in zip(iq_ids, graded_answers):
        cur.execute(
            "UPDATE InterviewQuestions SET score = ?, notes = ? WHERE id = ?",
            ga.score, ga.notes, iq_id,
        )


def _save_scores_and_complete(
    cur,
    interview_id: str,
    iq_ids: list[str],
    graded_answers,
    overall_score: float,
    interview_result: str,
    ai_feedback: str | None = None,
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
        SET status = ?, result = ?, feedback = ?, completed_at = GETDATE()
        WHERE id = ?
        """,
        interview_result, overall_score, ai_feedback, interview_id,
    )
    if interview_result == "Failed":
        _mark_subsequent_rounds_not_needed(cur, interview_id)
    elif interview_result == "Pass":
        _maybe_mark_hired(cur, interview_id)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def get_interview_questions(interview_id: str, test_mode: bool = False) -> list[QuestionItem]:
    if test_mode:
        cached = _test_mode_questions.get(interview_id)
        if cached:
            return cached
    conn = get_connection()
    try:
        cur = conn.cursor()
        return _fetch_existing_questions(cur, interview_id)
    finally:
        conn.close()


def merge_test_mode_answers(interview_id: str, extracted: list[dict]) -> None:
    """
    Test-mode equivalent of save_voice_answers_bulk for oral interviews — stores
    extracted candidate answers into the in-memory cache instead of writing to
    InterviewQuestions, so test voice interviews never touch the DB.

    `extracted` items:
        question : str
        answer   : str

    Replaces whatever was cached for this interview_id.
    """
    def _make_item(item: dict) -> QuestionItem:
        new_id = str(uuid.uuid4())
        return QuestionItem(
            iq_id=new_id,
            question_id=new_id,
            question_text=str(item.get("question") or ""),
            candidate_answer=str(item.get("answer") or ""),
            score=None,
            notes=None,
        )

    _test_mode_questions[interview_id] = [_make_item(item) for item in extracted]


def clear_test_mode_cache(interview_id: str) -> None:
    _test_mode_questions.pop(interview_id, None)


def save_voice_answers_bulk(interview_id: str, extracted: list[dict]) -> None:
    """
    Persist voice-interview answers from LLM extraction.

    Each item in `extracted` must have:
        question : str — question text
        answer   : str — candidate answer (non-empty)

    If InterviewQuestions rows already exist for this interview, delete them,
    then insert `extracted` as fresh Questions + InterviewQuestions rows.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM InterviewQuestions WHERE interview_id = ?", interview_id)
        if cur.fetchall():
            cur.execute("DELETE FROM InterviewQuestions WHERE interview_id = ?", interview_id)

        for item in extracted:
            question_text = str(item.get("question") or "")
            answer = str(item.get("answer") or "")

            new_q_id = str(uuid.uuid4())
            new_iq_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO Questions
                    (id, interview_round_type_id, job_role_id, experience_level_id,
                     question_text, is_active, ai_generated, created_at)
                VALUES (?, NULL, NULL, NULL, ?, 1, 1, GETDATE())
                """,
                new_q_id,
                question_text,
            )
            cur.execute(
                """
                INSERT INTO InterviewQuestions
                    (id, interview_id, question_id, candidate_answer, score, notes)
                VALUES (?, ?, ?, ?, NULL, NULL)
                """,
                new_iq_id, interview_id, new_q_id, answer,
            )

        conn.commit()
    finally:
        conn.close()


def _fetch_current_status(cur, interview_id: str) -> str:
    cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
    row = cur.fetchone()
    return str(row[0]) if row else "In Progress"


def mark_interview_terminated(interview_id: str, reason: str) -> None:
    """Mark an interview Failed for any terminal cause the caller has already
    decided on (misconduct, no-response timeout, weak performance, processing
    failure, etc.) — persists status=Failed with the caller's actual `reason`
    as feedback. Idempotent: no-ops if already Pass/Failed."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if _fetch_current_status(cur, interview_id).lower() in ("pass", "failed"):
            return
        cur.execute(
            """UPDATE Interviews
               SET status = 'Failed', result = ?, feedback = ?, completed_at = GETDATE()
               WHERE id = ?""",
            0.0, reason, interview_id,
        )
        _mark_subsequent_rounds_not_needed(cur, interview_id)
        conn.commit()
    finally:
        conn.close()


def mark_interview_failed_on_leave(interview_id: str, interview_type: str = "written") -> None:
    """Force-fail an interview when the candidate leaves mid-session (tab switch / logout / refresh)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        vr = validate_interview(ValidationInput(
            event_type="tab_switch",
            computed_score=0.0,
            failing_criteria=PASS_THRESHOLD,
            enable_fail_cases=settings.ENABLE_FAIL_CASES,
            current_status=_fetch_current_status(cur, interview_id),
            interview_type=interview_type,
        ))
        if vr.applied_rule == "idempotency_guard":
            return
        cur.execute(
            """UPDATE Interviews
               SET status = ?, result = ?, feedback = ?, completed_at = GETDATE()
               WHERE id = ?""",
            vr.final_status, vr.final_score, vr.final_feedback, interview_id,
        )
        if vr.final_status == "Failed":
            _mark_subsequent_rounds_not_needed(cur, interview_id)
        conn.commit()
    finally:
        conn.close()


async def generate_interview_questions(
    interview_id: str,
    return_questions: bool = True,
    test_mode: bool = False,
) -> GenerateQuestionsResponse:
    # --- 1. Fetch interview context ---
    ctx = get_interview_context(interview_id)
    interview_type = ctx["interview_type"]
    candidate_id = ctx["candidate_id"]
    job_posting_id = ctx["job_posting_id"]
    application_id = ctx["application_id"]
    interview_round_type_id = ctx["interview_round_type_id"]
    job_role_id = ctx["job_role_id"]

    # --- 2. Fetch existing questions + experience level ---
    conn = get_connection()
    try:
        cur = conn.cursor()
        existing = _fetch_existing_questions(cur, interview_id)
        cur.execute(
            "SELECT experience_level_id FROM CandidateProfiles WHERE id = ?",
            candidate_id,
        )
        cp_row = cur.fetchone()
        experience_level_id = int(cp_row[0]) if cp_row and cp_row[0] else 1
        cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
        current_status_row = cur.fetchone()
    finally:
        conn.close()

    # In test mode with an already-completed interview: return cached/existing
    # questions without touching the DB at all.
    if test_mode and current_status_row and str(current_status_row[0]).lower() in ("pass", "failed"):
        items = _test_mode_questions.get(interview_id) or existing or []
        return GenerateQuestionsResponse(
            interview_id=interview_id,
            questions=items if return_questions else [],
            timer_seconds=TIMER_SECONDS,
            interview_type=interview_type,
            enable_fail_cases=settings.ENABLE_FAIL_CASES,
        )

    # --- 3. Always generate fresh questions via AI ---
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

    new_texts = [q.question_text for q in result["questions"]]

    if test_mode:
        # Test mode never touches Questions/InterviewQuestions — questions live only
        # in the in-memory cache, keyed by interview_id, so test runs can't drift out
        # of sync with (or pollute) real DB rows.
        items = [
            QuestionItem(
                iq_id=str(uuid.uuid4()),
                question_id=str(uuid.uuid4()),
                question_text=text,
                candidate_answer=None,
                score=None,
                notes=None,
            )
            for text in new_texts
        ]
        _test_mode_questions[interview_id] = items
    else:
        # Real generation for this interview_id — any leftover test-mode cache
        # entry is now stale and must never resurface for this ID again.
        clear_test_mode_cache(interview_id)

        # --- 4. Upsert: update existing rows or insert new ones ---
        conn = get_connection()
        try:
            cur = conn.cursor()
            if current_status_row and str(current_status_row[0]).lower() in ("pass", "failed", "not needed"):
                raise ValueError(
                    f"Interview {interview_id} is already completed ({current_status_row[0]}) "
                    "and cannot be restarted."
                )

            if existing:
                items = _update_generated_questions(
                    cur, interview_id, existing, new_texts,
                    interview_round_type_id, job_role_id, experience_level_id,
                )
            else:
                items = _store_generated_questions(
                    cur,
                    interview_id,
                    new_texts,
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
        enable_fail_cases=settings.ENABLE_FAIL_CASES,
    )


async def score_interview_answers(
    interview_id: str,
    fetch_from_db: bool,
    answers: list[AnswerItem],
    event_type: str = "submit",
    interview_type: str = "written",
    test_mode: bool = False,
) -> ScoreAnswersResponse:
    if not fetch_from_db and not answers:
        raise ValueError("No answers submitted and fetch_from_db is False")

    # test_mode interviews never have DB rows for their questions — use the
    # in-memory cache populated by generate_interview_questions instead.
    cached = _test_mode_questions.get(interview_id) if test_mode else None

    # --- 1. Fetch questions and build list to score ---
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
        status_row = cur.fetchone()
        if not status_row:
            raise ValueError(f"Interview {interview_id} not found")

        # In normal mode, block re-submitting new answers to a completed interview.
        # Display-only scoring (fetch_from_db=True — e.g. the voice agent already
        # concluded pass/fail and the frontend just wants the graded breakdown) is
        # always allowed; the idempotency check below prevents it from flipping an
        # already-final status.
        if not test_mode and not fetch_from_db and str(status_row[0]).lower() in ("pass", "failed", "not needed"):
            raise ValueError("This interview has already been completed and cannot be rescored.")

        stored = cached if cached else _fetch_existing_questions(cur, interview_id)
        if not stored:
            raise ValueError(f"No questions found for interview {interview_id}")

        if fetch_from_db:
            to_score = stored
        else:
            if not test_mode:
                # Only persist candidate answers in normal mode.
                _save_candidate_answers(cur, interview_id, answers)
                conn.commit()
            iq_map = {q.iq_id.lower(): q for q in stored}
            to_score = [
                QuestionItem(
                    iq_id=a.iq_id,
                    question_id=iq_map[a.iq_id.lower()].question_id if a.iq_id.lower() in iq_map else "",
                    question_text=iq_map[a.iq_id.lower()].question_text if a.iq_id.lower() in iq_map else a.iq_id,
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
    state: AgentState = {"answers": ai_answers, "interview_type": interview_type}
    result = await score_answers_tool(state)
    if result["status"] != "success":
        raise RuntimeError("AI answer scoring failed")

    # --- 3. Validate result ---
    vr = validate_interview(ValidationInput(
        event_type=event_type,
        computed_score=result["overall_score"],
        failing_criteria=PASS_THRESHOLD,
        enable_fail_cases=settings.ENABLE_FAIL_CASES,
        current_status=str(status_row[0]),
        interview_type=interview_type,
    ))

    if not test_mode:
        # --- 4. Persist scores (normal mode only) ---
        conn = get_connection()
        try:
            cur = conn.cursor()
            if vr.applied_rule == "idempotency_guard":
                # Status/feedback are already final (voice agent already concluded
                # pass/fail) — only fill in per-question scores, don't touch them.
                _save_question_scores(cur, [item.iq_id for item in to_score], result["graded_answers"])
            else:
                _save_scores_and_complete(
                    cur, interview_id,
                    [item.iq_id for item in to_score],
                    result["graded_answers"],
                    vr.final_score, vr.final_status,
                    vr.final_feedback or None,
                )
            conn.commit()
        finally:
            conn.close()

    return ScoreAnswersResponse(
        overall_score=vr.final_score,
        total_graded=result["total_graded"],
        graded_answers=[
            GradedAnswer(
                question_text=to_score[i].question_text,
                candidate_answer=g.candidate_answer,
                score=g.score,
                notes=g.notes,
            )
            for i, g in enumerate(result["graded_answers"])
        ],
        result=vr.final_status,
    )
