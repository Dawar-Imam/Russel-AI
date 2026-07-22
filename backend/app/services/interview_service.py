import asyncio
import json
import logging
import random
import uuid
from datetime import datetime

from app.ai.ai_services.answer_scoring_service import grade_candidate_answers
from app.ai.ai_services.cv_relevance_service import fetch_candidate_cv_relevance
from app.ai.ai_services.question_bank_service import fetch_interview_context
from app.ai.ai_services.question_generation_service import generate_questions
from app.ai.interview_tools.schemas import (
    AnswerItem as AIAnswerItem,
    CandidateCVRelevance,
    GradedAnswer as AIGradedAnswer,
    QuestionItem as AIQuestionItem,
)
from app.core.config import settings
from app.database import db_cursor
from app.schemas.interviews import (
    AnswerItem,
    GenerateQuestionsResponse,
    GradedAnswer,
    QuestionItem,
    ScoreAnswersResponse,
)
from app.services.interview_validator import (
    SCORED_STATUSES,
    TERMINAL_ROUND_STATUSES,
    ValidationInput,
    WRITTEN_TEST_MIN_CORRECT,
    validate_interview,
)
from app.services.question_order_service import dedupe_order_and_options, record_round_history
from app.services.pregen_lock import (
    PREGEN_LOCK_WAIT_TIMEOUT_SECONDS as _PREGEN_LOCK_WAIT_TIMEOUT_SECONDS,
    PREGEN_LOCK_POLL_INTERVAL_SECONDS as _PREGEN_LOCK_POLL_INTERVAL_SECONDS,
    acquire_pregen_lock as _acquire_pregen_lock,
    release_pregen_lock as _release_pregen_lock,
)

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 6.0
WRITTEN_TEST_QUESTION_COUNT = 15
CORRECT_ANSWER_SCORE_THRESHOLD = 7
# Default written-round duration when the recruiter didn't set InterviewRounds.time_limit_minutes.
# Oral rounds keep using settings.INTERVIEW_DURATION_MINUTES instead (see _limit_seconds).
WRITTEN_TEST_DEFAULT_DURATION_MINUTES = 45
# Extra time past a round's configured limit before autosave stops accepting new
# answers — absorbs normal request latency around the exact expiry instant so a
# save already in flight when the timer hits 0 doesn't get dropped.
EXPIRY_GRACE_SECONDS = 30

LEAVE_FEEDBACK = "User left the interview, interview automatically closed."


def _limit_seconds(time_limit_minutes: int | None, is_oral: bool = False) -> int:
    if time_limit_minutes:
        return time_limit_minutes * 60
    if is_oral:
        return settings.INTERVIEW_DURATION_MINUTES * 60
    return WRITTEN_TEST_DEFAULT_DURATION_MINUTES * 60


def _remaining_seconds(started_at: "datetime | None", limit_seconds: int) -> int:
    """Refresh-safe timer: once a round has actually started, remaining time is
    computed from the wall-clock elapsed since then, not reset to the full limit
    on every generate-questions call. Assumes the app and DB server clocks are
    close enough to compare directly (single-deployment assumption)."""
    if started_at is None:
        return limit_seconds
    elapsed = (datetime.now() - started_at).total_seconds()
    return max(0, int(limit_seconds - elapsed))


def _poll_existing_questions(interview_id: str) -> list[QuestionItem]:
    """Blocking DB read — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        return _fetch_existing_questions(cur, interview_id)


async def _wait_for_pregenerated_questions(interview_id: str) -> list[QuestionItem]:
    """Poll for rows written by whoever currently holds the pregen lock for this
    interview_id, instead of starting a duplicate LLM call. Returns [] on timeout —
    caller then retries acquiring the lock itself rather than waiting indefinitely."""
    elapsed = 0.0
    while elapsed < _PREGEN_LOCK_WAIT_TIMEOUT_SECONDS:
        await asyncio.sleep(_PREGEN_LOCK_POLL_INTERVAL_SECONDS)
        elapsed += _PREGEN_LOCK_POLL_INTERVAL_SECONDS
        found = await asyncio.to_thread(_poll_existing_questions, interview_id)
        if found:
            return found
    return []

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

class InterviewDeletedPostFailError(Exception):
    """Raised by get_interview_context when interview_id doesn't resolve to a live
    Interviews row because it was tombstoned in DeletedInterviewRounds — i.e. a
    recruiter's ATS rerun reset this candidate's pipeline (application_service.
    _delete_all_interviews removed it, unconditionally — a rerun never runs against a
    round still In Progress in the first place, that's excluded upstream). Distinct from
    a plain ValueError (bad/unknown interview_id, or any other not-found reason) so the
    API layer can return a specific 410 instead of a generic 404 — see
    app/api/endpoints/interviews.py generate_questions().

    Never confused with "questions not yet generated for this round": that case always
    has a live Interviews row (created at ATS-pass time, status 'Scheduled', zero
    InterviewQuestions rows) and never reaches the not-found branch below at all.

    Carries application_id — the interview-room frontend only has interview_id in scope
    (route param), but the redirect target (/application-progress/:applicationId) needs
    the application_id, which is unrecoverable any other way once the Interviews row
    (the only thing that used to link interview_id -> application_id) is gone.
    """

    def __init__(self, message: str, application_id: str) -> None:
        super().__init__(message)
        self.application_id = application_id


def get_interview_context(interview_id: str) -> dict:
    """Fetch all context needed for question generation from the interview record."""
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT
                i.application_id,
                a.job_id              AS job_posting_id,
                ir.interview_round_type_id,
                jp.job_role_id,
                a.candidate_id,
                irt.name              AS interview_type,
                ir.id                 AS interview_round_id,
                ir.time_limit_minutes
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
            cur.execute("SELECT application_id FROM DeletedInterviewRounds WHERE interview_id = ?", interview_id)
            tombstone = cur.fetchone()
            if tombstone:
                raise InterviewDeletedPostFailError(
                    f"Interview {interview_id} was deleted after an ATS-rerun fail",
                    application_id=str(tombstone[0]),
                )
            raise ValueError(f"Interview {interview_id} not found")
        return {
            "application_id": str(row[0]),
            "job_posting_id": str(row[1]),
            "interview_round_type_id": int(row[2]),
            "job_role_id": int(row[3]),
            "candidate_id": str(row[4]),
            "interview_type": str(row[5]) if row[5] else "",
            "interview_round_id": str(row[6]),
            "time_limit_minutes": int(row[7]) if row[7] is not None else None,
        }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _parse_options(options_json: str | None) -> tuple[list[str] | None, str | None]:
    """Questions.options stores {"choices": [...], "correct_option": "..."} for MCQs, NULL otherwise."""
    if not options_json:
        return None, None
    try:
        parsed = json.loads(options_json)
    except (TypeError, ValueError):
        return None, None
    return parsed.get("choices"), parsed.get("correct_option")


def _fetch_existing_questions(cur, interview_id: str) -> list[QuestionItem]:
    """Return questions for this interview with complete data from both tables."""
    cur.execute(
        """
        SELECT iq.id, iq.question_id, q.question_text, q.question_type, q.options,
               iq.candidate_answer, iq.score, iq.notes
        FROM InterviewQuestions iq
        JOIN Questions q ON q.id = iq.question_id
        WHERE iq.interview_id = ?
        ORDER BY iq.id
        """,
        interview_id,
    )
    items = []
    for r in cur.fetchall():
        choices, correct_option = _parse_options(r[4])
        items.append(QuestionItem(
            iq_id=str(r[0]),
            question_id=str(r[1]),
            question_text=r[2],
            question_type=r[3] or "short_answer",
            options=choices,
            correct_option=correct_option,
            candidate_answer=r[5],
            score=float(r[6]) if r[6] is not None else None,
            notes=r[7],
        ))
    return items


def _shuffle_and_serialize_options(
    item: AIQuestionItem, job_posting_id: str
) -> tuple[list[str] | None, str | None]:
    """Serializes an MCQ's options into the JSON blob Questions.options stores.
    `item.options` is expected to already be in its final per-candidate order —
    question_order_service.dedupe_order_and_options shuffles order once, per round,
    before any of these items reach here, so no shuffling happens at this
    layer anymore. `job_posting_id` is accepted for call-site compatibility
    with existing callers but is no longer used. correct_option is stored as
    literal text, matched by value at grading time — no index remapping needed."""
    if item.question_type != "mcq" or not item.options:
        return None, None
    options_json = json.dumps({"choices": item.options, "correct_option": item.correct_option})
    return item.options, options_json


def _update_generated_questions(
    cur,
    interview_id: str,
    existing: list[QuestionItem],
    new_items: list[AIQuestionItem],
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    job_posting_id: str,
) -> list[QuestionItem]:
    """UPDATE Questions in-place, paired by position with new_items.

    If the freshly generated count differs from `existing` (e.g. a regenerate
    that produces more/fewer questions than a prior attempt), surplus old rows
    are deleted and/or extra rows are inserted — the InterviewQuestions set
    always exactly matches the new generation, so no stale leftover question
    from a previous attempt can ever resurface alongside the new ones.
    """
    paired = min(len(existing), len(new_items))
    updated: list[QuestionItem] = []
    for item, new_q in zip(existing[:paired], new_items[:paired]):
        shuffled_options, options_json = _shuffle_and_serialize_options(new_q, job_posting_id)
        cur.execute(
            "UPDATE Questions SET question_text = ?, question_type = ?, options = ? WHERE id = ?",
            new_q.question_text, new_q.question_type, options_json, item.question_id,
        )
        updated.append(QuestionItem(
            iq_id=item.iq_id,
            question_id=item.question_id,
            question_text=new_q.question_text,
            question_type=new_q.question_type,
            options=shuffled_options,
            correct_option=new_q.correct_option,
            candidate_answer=item.candidate_answer,
            score=item.score,
            notes=item.notes,
        ))

    for stale in existing[paired:]:
        cur.execute("DELETE FROM InterviewQuestions WHERE id = ?", stale.iq_id)
        cur.execute("DELETE FROM Questions WHERE id = ?", stale.question_id)

    extra_items = new_items[paired:]
    if extra_items:
        updated.extend(store_generated_questions(
            cur, interview_id, extra_items,
            interview_round_type_id, job_role_id, experience_level_id, job_posting_id,
        ))

    return updated


def store_generated_questions(
    cur,
    interview_id: str,
    questions: list[AIQuestionItem],
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    job_posting_id: str,
) -> list[QuestionItem]:
    """Insert into Questions + InterviewQuestions; return items with full data."""
    items: list[QuestionItem] = []
    for q in questions:
        q_id = str(uuid.uuid4())
        iq_id = str(uuid.uuid4())
        shuffled_options, options_json = _shuffle_and_serialize_options(q, job_posting_id)
        cur.execute(
            """
            INSERT INTO Questions
                (id, interview_round_type_id, job_role_id, experience_level_id,
                 question_text, question_type, options, is_active, ai_generated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, GETDATE())
            """,
            q_id, interview_round_type_id, job_role_id, experience_level_id,
            q.question_text, q.question_type, options_json,
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
            question_text=q.question_text,
            question_type=q.question_type,
            options=shuffled_options,
            correct_option=q.correct_option,
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


def save_candidate_answer(interview_id: str, iq_id: str, candidate_answer: str) -> None:
    """Immediate per-answer persistence while a candidate is still taking a written
    round — called from the /save-answer endpoint on every autosave, so a
    refresh/crash/network drop never loses progress. No-ops once the round is
    terminal (Pass/Failed/Not Needed) so a stray in-flight autosave can never
    resurrect answer data after the round is already scored. Also no-ops once the
    round's time limit + EXPIRY_GRACE_SECONDS has elapsed — this is the actual
    server-side stop on a candidate continuing to answer past the configured limit
    by tampering with (or just not running) the client-side timer; the client's
    own auto-submit is a UX nicety, not the enforcement boundary."""
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT i.status, i.started_at, ir.time_limit_minutes
            FROM Interviews i JOIN InterviewRounds ir ON ir.id = i.interview_round_id
            WHERE i.id = ?
            """,
            interview_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Interview {interview_id} not found")
        if str(row[0]).lower() in TERMINAL_ROUND_STATUSES:
            return
        started_at = row[1]
        if started_at is not None:
            limit_seconds = _limit_seconds(row[2])
            elapsed = (datetime.now() - started_at).total_seconds()
            if elapsed > limit_seconds + EXPIRY_GRACE_SECONDS:
                logger.info(
                    "save_candidate_answer: interview_id=%s past time limit + grace, ignoring autosave",
                    interview_id,
                )
                return
        _save_candidate_answers(cur, interview_id, [AnswerItem(iq_id=iq_id, candidate_answer=candidate_answer)])
        conn.commit()


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


def find_next_scheduled_round(cur, application_id: str, min_round_order: int = 0) -> str | None:
    """Return the Interviews.id of the earliest still-Scheduled round for this
    application with round_order > min_round_order, or None if there isn't one.

    Single shared "what's the next round" lookup — used both when ATS first passes
    (min_round_order=0, application_service.py) and when a round is scored Pass
    (min_round_order=<that round's order>, _save_scores_and_complete below) to decide
    which round's questions to pre-generate next.
    """
    cur.execute(
        """
        SELECT TOP 1 i.id
        FROM Interviews i
        JOIN InterviewRounds ir ON ir.id = i.interview_round_id
        WHERE i.application_id = ?
          AND i.status = 'Scheduled'
          AND ir.round_order > ?
        ORDER BY ir.round_order
        """,
        application_id, min_round_order,
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


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
) -> str | None:
    """Returns the next round's Interviews.id to pre-generate questions for, if this
    result was a Pass and a next round exists — the caller fires the Celery trigger
    for it after commit. None on Failed, or when there's no next round."""
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
        return None
    elif interview_result == "Pass":
        _maybe_mark_hired(cur, interview_id)
        cur.execute(
            """
            SELECT i.application_id, ir.round_order
            FROM Interviews i
            JOIN InterviewRounds ir ON ir.id = i.interview_round_id
            WHERE i.id = ?
            """,
            interview_id,
        )
        row = cur.fetchone()
        if row:
            return find_next_scheduled_round(cur, str(row[0]), min_round_order=int(row[1]))
    return None


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def get_interview_questions(interview_id: str, test_mode: bool = False) -> list[QuestionItem]:
    if test_mode:
        cached = _test_mode_questions.get(interview_id)
        if cached:
            return cached
    with db_cursor() as (conn, cur):
        return _fetch_existing_questions(cur, interview_id)


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
    with db_cursor() as (conn, cur):
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


def _fetch_current_status(cur, interview_id: str) -> str:
    cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
    row = cur.fetchone()
    return str(row[0]) if row else "In Progress"


def mark_interview_terminated(interview_id: str, reason: str) -> None:
    """Mark an interview Failed for any terminal cause the caller has already
    decided on (misconduct, no-response timeout, weak performance, processing
    failure, etc.) — persists status=Failed with the caller's actual `reason`
    as feedback. Idempotent: no-ops if already Pass/Failed."""
    with db_cursor() as (conn, cur):
        if _fetch_current_status(cur, interview_id).lower() in SCORED_STATUSES:
            return
        cur.execute(
            """UPDATE Interviews
               SET status = 'Failed', result = ?, feedback = ?, completed_at = GETDATE()
               WHERE id = ?""",
            0.0, reason, interview_id,
        )
        _mark_subsequent_rounds_not_needed(cur, interview_id)
        conn.commit()


def mark_interview_failed_on_leave(interview_id: str, interview_type: str = "written") -> None:
    """Force-fail an interview when the candidate leaves mid-session (tab switch / logout / refresh)."""
    with db_cursor() as (conn, cur):
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


def _fetch_generation_context(interview_id: str, candidate_id: str):
    """Blocking DB read — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        existing = _fetch_existing_questions(cur, interview_id)
        cur.execute(
            "SELECT experience_level_id FROM CandidateProfiles WHERE id = ?",
            candidate_id,
        )
        cp_row = cur.fetchone()
        experience_level_id = int(cp_row[0]) if cp_row and cp_row[0] else 1
        cur.execute("SELECT status, started_at FROM Interviews WHERE id = ?", interview_id)
        current_status_row = cur.fetchone()
    return existing, experience_level_id, current_status_row


def _mark_in_progress(interview_id: str) -> None:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop.
    started_at is set only the first time (COALESCE-guarded) — a later refresh must
    never push the deadline back out."""
    with db_cursor() as (conn, cur):
        cur.execute(
            "UPDATE Interviews SET status = 'In Progress', started_at = COALESCE(started_at, GETDATE()) WHERE id = ?",
            interview_id,
        )
        conn.commit()


def _upsert_generated_questions(
    interview_id: str,
    current_status_row,
    existing: list[QuestionItem],
    new_items: list[AIQuestionItem],
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    job_posting_id: str,
    interview_round_id: str,
) -> list[QuestionItem]:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        if current_status_row and str(current_status_row[0]).lower() in TERMINAL_ROUND_STATUSES:
            raise ValueError(
                f"Interview {interview_id} is already completed ({current_status_row[0]}) "
                "and cannot be restarted."
            )

        # Randomise question order and MCQ option order against the round's last
        # few candidates (read from Redis) before persisting.
        new_items = dedupe_order_and_options(interview_round_id, new_items)

        if existing:
            items = _update_generated_questions(
                cur, interview_id, existing, new_items,
                interview_round_type_id, job_role_id, experience_level_id, job_posting_id,
            )
        else:
            items = store_generated_questions(
                cur,
                interview_id,
                new_items,
                interview_round_type_id,
                job_role_id,
                experience_level_id,
                job_posting_id,
            )
        cur.execute(
            "UPDATE Interviews SET status = 'In Progress', started_at = COALESCE(started_at, GETDATE()) WHERE id = ?",
            interview_id,
        )
        conn.commit()
    # Record this candidate's final order into the round's Redis history only after
    # the SQL write has committed — matches the old mcq_redis_cache push-after-commit
    # ordering, so a rolled-back write never leaves a Redis entry for questions that
    # were never actually stored.
    record_round_history(interview_round_id, new_items)
    return items


async def generate_interview_questions(
    interview_id: str,
    return_questions: bool = True,
    test_mode: bool = False,
) -> GenerateQuestionsResponse:
    # --- 1. Fetch interview context ---
    ctx = await asyncio.to_thread(get_interview_context, interview_id)
    interview_type = ctx["interview_type"]
    candidate_id = ctx["candidate_id"]
    job_posting_id = ctx["job_posting_id"]
    application_id = ctx["application_id"]
    interview_round_type_id = ctx["interview_round_type_id"]
    job_role_id = ctx["job_role_id"]
    interview_round_id = ctx["interview_round_id"]
    # Same substring convention used elsewhere (question_pregeneration_service.py,
    # InterviewRoom.tsx) — working off the raw InterviewRoundTypes.name value.
    is_oral = "oral" in interview_type.lower() or "voice" in interview_type.lower()
    limit_seconds = _limit_seconds(ctx["time_limit_minutes"], is_oral)

    # --- 2. Fetch existing questions + experience level ---
    existing, experience_level_id, current_status_row = await asyncio.to_thread(
        _fetch_generation_context, interview_id, candidate_id
    )
    started_at = current_status_row[1] if current_status_row else None

    # In test mode with an already-completed interview: return cached/existing
    # questions without touching the DB at all.
    if test_mode and current_status_row and str(current_status_row[0]).lower() in SCORED_STATUSES:
        items = _test_mode_questions.get(interview_id) or existing or []
        return GenerateQuestionsResponse(
            interview_id=interview_id,
            questions=items if return_questions else [],
            timer_seconds=limit_seconds,
            interview_type=interview_type,
            enable_fail_cases=settings.ENABLE_FAIL_CASES,
        )

    # Existing-questions gate: whenever InterviewQuestions already exist for this
    # interview_id — whether pre-generated by the background Celery task
    # (status still 'Scheduled') or written by an earlier call to this same
    # function (status already 'In Progress', e.g. the candidate refreshed
    # mid-test) — never call the LLM again. Regenerating here would silently
    # rewrite question text out from under an in-progress candidate while their
    # old candidate_answer/score stay attached to the same InterviewQuestions
    # rows. Not applied in test_mode, which never shares rows with the real
    # generation path.
    if not test_mode and existing:
        if current_status_row and str(current_status_row[0]).lower() in TERMINAL_ROUND_STATUSES:
            raise ValueError(
                f"Interview {interview_id} is already completed ({current_status_row[0]}) "
                "and cannot be restarted."
            )
        await asyncio.to_thread(_mark_in_progress, interview_id)
        # started_at is None the very first time a pre-generated round is opened
        # (pregeneration never touches it) — _remaining_seconds treats that as "just
        # starting now" and returns the full limit, same as _mark_in_progress setting
        # started_at=GETDATE() for the first time in that same call. Every later
        # refresh has a real started_at, so remaining time counts down correctly
        # instead of resetting to the full limit on each reload.
        return GenerateQuestionsResponse(
            interview_id=interview_id,
            questions=existing if return_questions else [],
            timer_seconds=_remaining_seconds(started_at, limit_seconds),
            interview_type=interview_type,
            enable_fail_cases=settings.ENABLE_FAIL_CASES,
        )

    # This is a genuine first-generation (existing empty, not test_mode) — the only case
    # that can race with a concurrent pregenerate_interview_questions call for the same
    # interview_id. Acquire the same lock pre-generation uses before any LLM call or DB
    # write; if pre-generation already holds it, wait for its result instead of starting
    # a duplicate generation, so the candidate never sees an empty state.
    holding_pregen_lock = False
    if not test_mode and not existing:
        holding_pregen_lock = _acquire_pregen_lock(interview_id)
        if not holding_pregen_lock:
            waited = await _wait_for_pregenerated_questions(interview_id)
            if waited:
                await asyncio.to_thread(_mark_in_progress, interview_id)
                return GenerateQuestionsResponse(
                    interview_id=interview_id,
                    questions=waited if return_questions else [],
                    timer_seconds=limit_seconds,
                    interview_type=interview_type,
                    enable_fail_cases=settings.ENABLE_FAIL_CASES,
                )
            # Waited the full timeout and nothing appeared yet — the original holder is
            # either still generating (unusually slow call) or crashed without releasing
            # (lock's 30s TTL will have expired by now in that case). Try to acquire once
            # more so our own write below stays serialized against it; if that still fails
            # (holder genuinely still alive past 25s), proceed unlocked as a last resort
            # rather than block the candidate indefinitely — loud log so it's visible.
            holding_pregen_lock = _acquire_pregen_lock(interview_id)
            if not holding_pregen_lock:
                logger.warning(
                    "generate_interview_questions: interview_id=%s pregen lock still held after %.0fs wait — "
                    "proceeding unlocked, a duplicate write is possible",
                    interview_id, _PREGEN_LOCK_WAIT_TIMEOUT_SECONDS,
                )

    try:
        # --- 3. Always generate fresh questions via AI ---
        context = await fetch_interview_context(
            interview_round_type_id=interview_round_type_id,
            job_role_id=job_role_id,
            experience_level_id=experience_level_id,
            job_posting_id=job_posting_id,
        )
        parsed_cv_text = await fetch_candidate_cv_relevance(application_id=application_id)
        candidate_relevance = CandidateCVRelevance(
            job_experience_summary=parsed_cv_text,
            relevant_skills=[],
            relevant_projects=[],
        )
        generated = await generate_questions(
            example_questions=[],
            candidate_relevance=candidate_relevance,
            count=WRITTEN_TEST_QUESTION_COUNT,
            context=context,
        )
        new_items = generated.generated_questions

        if test_mode:
            # Test mode never touches Questions/InterviewQuestions — questions live only
            # in the in-memory cache, keyed by interview_id, so test runs can't drift out
            # of sync with (or pollute) real DB rows. Options get a plain in-process
            # shuffle only (no cross-candidate dedup, no InterviewRounds history read/write —
            # test mode must never read or pollute real dedup history).
            items = [
                QuestionItem(
                    iq_id=str(uuid.uuid4()),
                    question_id=str(uuid.uuid4()),
                    question_text=q.question_text,
                    question_type=q.question_type,
                    options=(
                        random.sample(q.options, len(q.options))
                        if q.question_type == "mcq" and q.options else q.options
                    ),
                    correct_option=q.correct_option,
                    candidate_answer=None,
                    score=None,
                    notes=None,
                )
                for q in new_items
            ]
            _test_mode_questions[interview_id] = items
        else:
            # Real generation for this interview_id — any leftover test-mode cache
            # entry is now stale and must never resurface for this ID again.
            clear_test_mode_cache(interview_id)

            # --- 4. Upsert: update existing rows or insert new ones ---
            items = await asyncio.to_thread(
                _upsert_generated_questions,
                interview_id,
                current_status_row,
                existing,
                new_items,
                interview_round_type_id,
                job_role_id,
                experience_level_id,
                job_posting_id,
                interview_round_id,
            )
    finally:
        if holding_pregen_lock:
            _release_pregen_lock(interview_id)

    return GenerateQuestionsResponse(
        interview_id=interview_id,
        questions=items if return_questions else [],
        timer_seconds=limit_seconds,
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
    with db_cursor() as (conn, cur):
        cur.execute("SELECT status, application_id FROM Interviews WHERE id = ?", interview_id)
        status_row = cur.fetchone()
        if not status_row:
            raise ValueError(f"Interview {interview_id} not found")
        # Captured now, not looked up again later — used by the staleness redirect check
        # just below.
        application_id = str(status_row[1])

        # In normal mode, block re-submitting new answers to a completed interview.
        # Display-only scoring (fetch_from_db=True — e.g. the voice agent already
        # concluded pass/fail and the frontend just wants the graded breakdown) is
        # always allowed; the idempotency check below prevents it from flipping an
        # already-final status.
        if not test_mode and not fetch_from_db and str(status_row[0]).lower() in TERMINAL_ROUND_STATUSES:
            raise ValueError("This interview has already been completed and cannot be rescored.")

        # Stale-application redirect: same comparison job_service.select_applications_for_
        # ats_rerun and the post-completion hook further below already use (ats_run_version
        # behind the job's current ats_criteria_version, ATS_PENDING exempted) — checked
        # here too, before grading, so a candidate mid-interview whose job criteria changed
        # doesn't get scored against a stale round that's about to be wiped by the rerun
        # anyway. Gated the same way the terminal-round check above is (a genuine new
        # submission only, not test_mode or a display-only fetch_from_db replay).
        if not test_mode and not fetch_from_db:
            cur.execute(
                """
                SELECT a.job_id, a.status, a.ats_run_version, jp.ats_criteria_version
                FROM Applications a JOIN JobPostings jp ON jp.id = a.job_id
                WHERE a.id = ?
                """,
                application_id,
            )
            staleness_row = cur.fetchone()
            is_stale = (
                staleness_row is not None
                and str(staleness_row[1]) != "ATS_PENDING"
                and int(staleness_row[2]) < int(staleness_row[3])
            )
            if is_stale:
                # This round is never graded (no LLM call — it's about to be wiped by the
                # rerun anyway), but it must not be left 'In Progress': the dispatched
                # rerun's own is_excluded_from_ats_rerun check (application_service.py)
                # hard-excludes any application with an 'In Progress' interview, which
                # would otherwise make the rerun we're about to dispatch immediately
                # no-op (EXCLUDED, no publish_ats_completed, candidate stuck on
                # application-progress forever). Mirrors what _save_scores_and_complete
                # would set on a real Failed verdict — this row is tombstoned/deleted
                # moments later by _delete_all_interviews regardless of outcome.
                cur.execute(
                    "UPDATE Interviews SET status = 'Failed', completed_at = GETDATE() WHERE id = ?",
                    interview_id,
                )
                conn.commit()

                from app.services.ats_lock import set_latest_rerun_generation_batch
                from app.tasks import ats_rerun_tasks

                rerun_id = str(uuid.uuid4())
                set_latest_rerun_generation_batch([application_id], rerun_id)
                ats_rerun_tasks.run_batch.delay([application_id], None, rerun_id)
                return ScoreAnswersResponse(
                    overall_score=0,
                    total_graded=0,
                    graded_answers=[],
                    result="",
                    redirect_application_id=application_id,
                )

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
                    question_type=iq_map[a.iq_id.lower()].question_type if a.iq_id.lower() in iq_map else "short_answer",
                    correct_option=iq_map[a.iq_id.lower()].correct_option if a.iq_id.lower() in iq_map else None,
                    candidate_answer=a.candidate_answer,
                    score=None,
                    notes=None,
                )
                for a in answers
            ]

    # --- 2. Score answers via AI (no DB connection held during this) ---
    ai_answers = [
        AIAnswerItem(
            question_text=item.question_text,
            candidate_answer=item.candidate_answer or "",
            question_type=item.question_type,
            correct_option=item.correct_option,
        )
        for item in to_score
    ]
    graded = await grade_candidate_answers(ai_answers, interview_type=interview_type)

    # The LLM's structured output is not a trustworthy source of truth for what the
    # candidate actually submitted, or for how many answers it graded — models can
    # paraphrase or invent a `candidate_answer` echo instead of faithfully reproducing
    # a blank/nonsense input, and can under-count `graded_answers` relative to
    # `to_score` (the real, DB-backed question list). Reconcile positionally against
    # `to_score` so the result can never show text the candidate didn't write, never
    # silently drop a real question, and never award marks for a blank answer
    # regardless of what the LLM returned.
    while len(graded.graded_answers) < len(to_score):
        missing = to_score[len(graded.graded_answers)]
        graded.graded_answers.append(AIGradedAnswer(
            question_text=missing.question_text,
            candidate_answer="",
            score=0,
            notes="Not graded — missing from the AI scoring response.",
        ))
    for item, g in zip(to_score, graded.graded_answers):
        submitted = (item.candidate_answer or "").strip()
        g.candidate_answer = submitted if submitted else "(no answer)"
        if not submitted:
            g.score = 0

    correct_count = sum(
        1 for g in graded.graded_answers[:len(to_score)] if g.score >= CORRECT_ANSWER_SCORE_THRESHOLD
    )

    # --- 3. Validate result ---
    vr = validate_interview(ValidationInput(
        event_type=event_type,
        computed_score=graded.overall_score,
        failing_criteria=PASS_THRESHOLD,
        enable_fail_cases=settings.ENABLE_FAIL_CASES,
        current_status=str(status_row[0]),
        interview_type=interview_type,
        correct_count=correct_count,
    ))

    if not test_mode:
        # --- 4. Persist scores (normal mode only) ---
        next_round_to_pregenerate: str | None = None
        round_completed_now = vr.applied_rule != "idempotency_guard"
        with db_cursor() as (conn, cur):
            if vr.applied_rule == "idempotency_guard":
                # Status/feedback are already final (voice agent already concluded
                # pass/fail) — only fill in per-question scores, don't touch them.
                _save_question_scores(cur, [item.iq_id for item in to_score], graded.graded_answers)
            else:
                next_round_to_pregenerate = _save_scores_and_complete(
                    cur, interview_id,
                    [item.iq_id for item in to_score],
                    graded.graded_answers,
                    vr.final_score, vr.final_status,
                    vr.final_feedback or None,
                )
            conn.commit()

        if next_round_to_pregenerate:
            # Deliberately deferred: written_test_tasks.py imports
            # question_pregeneration_service.py, which imports this module — so a
            # top-level import here would reintroduce a circular import. This is a
            # one-directional dependency-inversion, not a workaround for an
            # unresolved cycle (see app/services/question_pregeneration_service.py).
            from app.tasks import written_test_tasks
            written_test_tasks.trigger.delay(next_round_to_pregenerate)

        # ATS staleness completion hook (Feature 1): only after commit, never inside the
        # transaction above — _persist_ats_rerun_result opens its own db_cursor() connection,
        # so calling it synchronously from within this still-open transaction risks a
        # self-lock. Dispatched the same way the manual "Rerun ATS" button does (Celery
        # batch task + a fresh generation token), so it can never race that path — whichever
        # dispatch is newer wins via ats_lock.is_latest_rerun_generation. round_completed_now
        # is False on the idempotency_guard branch above (round already concluded earlier via
        # the voice agent path, which already had its own chance to trigger this). This is a
        # second, later check than the pre-grading staleness redirect near the top of this
        # function — that one catches staleness before scoring even starts; this one catches
        # the narrow case where criteria changed in the brief window between that check and
        # this round's completion.
        if round_completed_now:
            # Local import — application_service.py imports CORRECT_ANSWER_SCORE_THRESHOLD
            # from this module at top level, so a top-level import here would be circular.
            from app.services.application_service import is_excluded_from_ats_rerun

            with db_cursor() as (conn, cur):
                cur.execute(
                    """
                    SELECT a.job_id, a.status, a.ats_run_version, jp.ats_criteria_version
                    FROM Applications a JOIN JobPostings jp ON jp.id = a.job_id
                    WHERE a.id = ?
                    """,
                    application_id,
                )
                row = cur.fetchone()
                is_stale = bool(row) and str(row[1]) != "ATS_PENDING" and int(row[2]) < int(row[3])
                is_excluded = (
                    is_stale
                    and is_excluded_from_ats_rerun(cur, application_id, str(row[0]))
                )

            if is_stale and not is_excluded:
                from app.services.ats_lock import set_latest_rerun_generation_batch
                from app.tasks import ats_rerun_tasks

                rerun_id = str(uuid.uuid4())
                set_latest_rerun_generation_batch([application_id], rerun_id)
                ats_rerun_tasks.run_batch.delay([application_id], None, rerun_id)

    return ScoreAnswersResponse(
        overall_score=vr.final_score,
        # len(to_score), not the LLM-reported graded.total_graded — total_graded is
        # self-counted by the model and can undercount relative to the actual
        # question set (see reconciliation above), which is what previously caused
        # the result page to show e.g. "2 out of 13" for a 15-question interview.
        total_graded=len(to_score),
        graded_answers=[
            GradedAnswer(
                question_text=item.question_text,
                candidate_answer=g.candidate_answer,
                score=g.score,
                notes=g.notes,
                is_correct=g.score >= CORRECT_ANSWER_SCORE_THRESHOLD,
            )
            for item, g in zip(to_score, graded.graded_answers)
        ],
        result=vr.final_status,
        improvement_recommendations=graded.improvement_recommendations,
        total_questions=len(to_score),
        passed_questions=correct_count,
        passing_threshold=WRITTEN_TEST_MIN_CORRECT,
    )
