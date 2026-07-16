import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from app.database import db_cursor
from app.schemas.applications import ATSCheckResponse, ATSRerunNotice, ApplyResponse, InterviewQuestionItem, InterviewRoundInfo, InterviewStagesResponse, MyApplicationItem
from app.services.ats_lock import acquire_ats_lock, release_ats_lock
from app.services.events import publish_ats_completed
from app.services.interview_service import CORRECT_ANSWER_SCORE_THRESHOLD, _parse_options

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("Scheduled", "In Progress")

# Application statuses that indicate ATS has already passed
_ATS_PASSED_STATUSES = ("ATS_PASS", "IN_PROGRESS", "HIRED")
_ATS_FAILED_STATUSES = ("ATS_FAIL", "REJECTED")

# Applications in these statuses are never candidates for a recruiter-triggered ATS rerun
# (see job_service.select_applications_for_ats_rerun) — the process is fully terminal.
_TERMINAL_APPLICATION_STATUSES = ("HIRED", "REJECTED")

_VERDICT_LABELS = {
    "ATS_PASS": "Passed",
    "ATS_FAIL": "Failed",
    "ATS_PENDING": "Pending",
    "ATS_ERROR": "Error",
    "IN_PROGRESS": "Passed (in interview process)",
    "HIRED": "Hired",
    "REJECTED": "Rejected",
}


def _parse_ats_details(raw: str | None) -> ATSCheckResponse | None:
    """Parse the stored `ats_details` JSON into an ATSCheckResponse.

    Returns None (rather than raising) on legacy/malformed JSON — e.g. rows persisted under a
    previous ATS response shape — so a schema change doesn't break stages/history for old
    applications; the endpoint falls back to a minimal status-derived response.
    """
    if not raw:
        return None
    try:
        return ATSCheckResponse(**json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        logger.warning("Failed to parse stored ats_details: %s", exc)
        return None


# ============================================================
# Recruiter-triggered ATS rerun
# ============================================================


def is_excluded_from_ats_rerun(cur, application_id: str, job_id: str) -> bool:
    """Recheck rerun eligibility at execution time — selection-time criteria (see
    job_service.select_applications_for_ats_rerun) can go stale between when a batch is
    dispatched and when this application's Celery task actually runs (e.g. a round failed,
    or the candidate cleared every round, in the interim)."""
    cur.execute("SELECT status FROM Applications WHERE id = ?", application_id)
    row = cur.fetchone()
    if not row:
        return True
    if str(row[0]) in _TERMINAL_APPLICATION_STATUSES:
        return True

    cur.execute("SELECT 1 FROM Interviews WHERE application_id = ? AND status = 'Failed'", application_id)
    if cur.fetchone():
        return True

    cur.execute(
        "SELECT COUNT(*) FROM InterviewRounds WHERE job_posting_id = ? AND is_active = 1",
        job_id,
    )
    total_rounds = int(cur.fetchone()[0])
    if total_rounds > 0:
        cur.execute(
            """
            SELECT COUNT(DISTINCT i.interview_round_id)
            FROM Interviews i
            JOIN InterviewRounds ir ON ir.id = i.interview_round_id
            WHERE i.application_id = ? AND ir.job_posting_id = ? AND i.status = 'Pass'
            """,
            application_id, job_id,
        )
        if int(cur.fetchone()[0]) == total_rounds:
            return True
    return False


def _insert_ats_history(
    cur,
    application_id: str,
    status: str,
    ats_details: str | None,
    ats_evaluated_at,
    ats_model_version: str | None,
    recruiter_id: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO ATSEvaluationHistory
            (id, application_id, status, ats_details, ats_evaluated_at, ats_model_version, triggered_by, recruiter_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'recruiter', ?, GETDATE())
        """,
        str(uuid.uuid4()), application_id, status, ats_details, ats_evaluated_at, ats_model_version, recruiter_id,
    )


def _delete_non_in_progress_interviews(cur, application_id: str) -> bool:
    """Delete every Interviews row (+ its InterviewQuestions) for this application that is
    NOT currently 'In Progress'. Returns True if an 'In Progress' row still remains — the
    caller must defer applying the rerun result until that round concludes rather than
    yank it out from under a live candidate session."""
    cur.execute(
        "SELECT 1 FROM Interviews WHERE application_id = ? AND status = 'In Progress'",
        application_id,
    )
    still_in_progress = cur.fetchone() is not None

    cur.execute(
        "SELECT id FROM Interviews WHERE application_id = ? AND status != 'In Progress'",
        application_id,
    )
    stale_ids = [str(r[0]) for r in cur.fetchall()]
    for iv_id in stale_ids:
        cur.execute("DELETE FROM InterviewQuestions WHERE interview_id = ?", iv_id)
        cur.execute("DELETE FROM Interviews WHERE id = ?", iv_id)

    return still_in_progress


def _delete_all_interviews(cur, application_id: str) -> None:
    cur.execute("SELECT id FROM Interviews WHERE application_id = ?", application_id)
    ids = [str(r[0]) for r in cur.fetchall()]
    for iv_id in ids:
        cur.execute("DELETE FROM InterviewQuestions WHERE interview_id = ?", iv_id)
        cur.execute("DELETE FROM Interviews WHERE id = ?", iv_id)


def apply_pending_ats_rerun(cur, application_id: str) -> bool:
    """Called right after an interview round is finalized (interview_service.
    _save_scores_and_complete) and defensively at the top of get_interview_stages(): if a
    recruiter's PASS->FAIL rerun landed while a round was still 'In Progress', the fail was
    deferred (see _persist_ats_rerun_result) rather than applied immediately so the
    candidate's live session was never disturbed. Once that round has concluded — Pass or
    Failed either way, the deferred FAIL always wins — apply it now. No-ops (returns False)
    if nothing is pending, or if some round is still In Progress.

    Caller commits; this function only executes statements on the given cursor.
    """
    cur.execute(
        """
        SELECT pending_ats_rerun_details, pending_ats_rerun_evaluated_at,
               pending_ats_rerun_model_version, pending_ats_rerun_recruiter_id
        FROM Applications WHERE id = ?
        """,
        application_id,
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False

    cur.execute(
        "SELECT 1 FROM Interviews WHERE application_id = ? AND status = 'In Progress'",
        application_id,
    )
    if cur.fetchone():
        return False

    pending_details, pending_evaluated_at, pending_model_version, pending_recruiter_id = row

    cur.execute(
        "SELECT status, ats_details, ats_evaluated_at, ats_model_version FROM Applications WHERE id = ?",
        application_id,
    )
    prev = cur.fetchone()
    _insert_ats_history(cur, application_id, str(prev[0]), prev[1], prev[2], prev[3], pending_recruiter_id)

    _delete_all_interviews(cur, application_id)

    cur.execute(
        """
        UPDATE Applications
        SET status = 'ATS_FAIL', ats_details = ?, ats_evaluated_at = ?, ats_model_version = ?,
            ats_rerun_count = ats_rerun_count + 1, ats_rerun_unseen = 1,
            pending_ats_rerun_details = NULL, pending_ats_rerun_evaluated_at = NULL,
            pending_ats_rerun_model_version = NULL, pending_ats_rerun_recruiter_id = NULL
        WHERE id = ?
        """,
        pending_details, pending_evaluated_at, pending_model_version, application_id,
    )
    logger.info("ATS rerun: applied deferred PASS->FAIL result for application_id=%s", application_id)
    return True


def _fetch_application_for_ats_rerun(application_id: str):
    """Blocking DB read — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT job_id, candidate_id, status, ats_details, ats_evaluated_at, ats_model_version, resume_id FROM Applications WHERE id = ?",
            application_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Application {application_id} not found")
        job_id, candidate_id, status = str(row[0]), str(row[1]), str(row[2])
        old_ats_details, old_evaluated_at, old_model_version = row[3], row[4], row[5]
        resume_id = str(row[6]) if row[6] else None

        excluded = is_excluded_from_ats_rerun(cur, application_id, job_id)

        parsed_text: str | None = None
        if resume_id:
            cur.execute("SELECT parsed_text FROM Resumes WHERE id = ?", resume_id)
            resume_row = cur.fetchone()
            if resume_row and resume_row[0]:
                parsed_text = str(resume_row[0])

    return job_id, candidate_id, status, old_ats_details, old_evaluated_at, old_model_version, parsed_text, excluded


def _persist_ats_rerun_result(
    application_id: str,
    job_id: str,
    recruiter_id: str | None,
    old_status: str,
    old_ats_details: str | None,
    old_evaluated_at,
    old_model_version: str | None,
    details_json: str,
    evaluated_at: datetime,
    model_version: str,
    new_verdict_pass: bool,
) -> tuple[str | None, bool]:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop.

    Returns (target_interview_id_to_pregenerate_or_None, deferred) — `deferred` is True when
    a PASS->FAIL rerun was computed but held back because a round is still In Progress.
    """
    target_interview_id: str | None = None
    deferred = False
    was_pass = old_status in _ATS_PASSED_STATUSES

    with db_cursor() as (conn, cur):
        # Re-check exclusion right before writing — time has passed since selection/fetch.
        if is_excluded_from_ats_rerun(cur, application_id, job_id):
            logger.info("ATS rerun: application_id=%s became excluded before write — skipping", application_id)
            return None, False

        _insert_ats_history(cur, application_id, old_status, old_ats_details, old_evaluated_at, old_model_version, recruiter_id)

        if was_pass and not new_verdict_pass:
            # PASS -> FAIL
            still_in_progress = _delete_non_in_progress_interviews(cur, application_id)
            if still_in_progress:
                cur.execute(
                    """
                    UPDATE Applications
                    SET pending_ats_rerun_details = ?, pending_ats_rerun_evaluated_at = ?,
                        pending_ats_rerun_model_version = ?, pending_ats_rerun_recruiter_id = ?
                    WHERE id = ?
                    """,
                    details_json, evaluated_at, model_version, recruiter_id, application_id,
                )
                deferred = True
            else:
                cur.execute(
                    """
                    UPDATE Applications
                    SET status = 'ATS_FAIL', ats_details = ?, ats_evaluated_at = ?, ats_model_version = ?,
                        ats_rerun_count = ats_rerun_count + 1, ats_rerun_unseen = 1
                    WHERE id = ?
                    """,
                    details_json, evaluated_at, model_version, application_id,
                )
        elif not was_pass and new_verdict_pass:
            # FAIL/PENDING/ERROR -> PASS: same "normal execution" as a first-time pass.
            cur.execute(
                """
                UPDATE Applications
                SET status = 'ATS_PASS', ats_details = ?, ats_evaluated_at = ?, ats_model_version = ?,
                    ats_rerun_count = ats_rerun_count + 1, ats_rerun_unseen = 1
                WHERE id = ?
                """,
                details_json, evaluated_at, model_version, application_id,
            )
            _create_interviews_for_application(cur, application_id, job_id)
            from app.services.interview_service import find_next_scheduled_round
            target_interview_id = find_next_scheduled_round(cur, application_id, min_round_order=0)
        else:
            # PASS -> PASS or FAIL -> FAIL: overwrite ats_details only, no status/interview change.
            new_status = "ATS_PASS" if new_verdict_pass else "ATS_FAIL"
            cur.execute(
                """
                UPDATE Applications
                SET ats_details = ?, ats_evaluated_at = ?, ats_model_version = ?,
                    ats_rerun_count = ats_rerun_count + 1, ats_rerun_unseen = 1
                WHERE id = ? AND status = ?
                """,
                details_json, evaluated_at, model_version, application_id, new_status,
            )

        conn.commit()

    return target_interview_id, deferred


async def rerun_ats_and_persist(application_id: str, recruiter_id: str | None = None) -> None:
    """Re-run the ATS LLM check for a single application (always live, never cached) and
    apply the recruiter-rerun decision matrix. Called from ats_rerun_tasks.run_single —
    the Celery task Job.rerun_ats_for_job dispatches per selected application_id.
    """
    acquired = acquire_ats_lock(application_id)
    if not acquired:
        logger.info("ATS rerun: application_id=%s already has a run in progress — skipping", application_id)
        return

    try:
        (
            job_id, candidate_id, old_status, old_ats_details, old_evaluated_at,
            old_model_version, parsed_text, excluded,
        ) = await asyncio.to_thread(_fetch_application_for_ats_rerun, application_id)

        if excluded:
            logger.info("ATS rerun: application_id=%s excluded from rerun — skipping", application_id)
            return

        from app.ai.ai_services.ats_service import ATSValidationError, check_ats_eligibility
        try:
            result, model_version = await check_ats_eligibility(
                candidate_id, job_id, parsed_text=parsed_text, application_id=application_id
            )
        except ATSValidationError:
            # Malformed LLM output: leave the previously-good ats_details/status untouched —
            # unlike the first-run path, a rerun has something worth preserving.
            logger.error("ATS rerun: validation failed for application_id=%s — leaving prior result untouched", application_id)
            return

        evaluated_at = datetime.now(timezone.utc)
        details_json = result.model_dump_json()

        target_interview_id, deferred = await asyncio.to_thread(
            _persist_ats_rerun_result,
            application_id, job_id, recruiter_id,
            old_status, old_ats_details, old_evaluated_at, old_model_version,
            details_json, evaluated_at, model_version,
            result.final_verdict == "PASS",
        )

        if target_interview_id:
            from app.tasks import written_test_tasks
            written_test_tasks.trigger.delay(target_interview_id)

        if not deferred:
            await publish_ats_completed(
                application_id,
                {
                    "event": "ats_completed",
                    "application_id": application_id,
                    "status": "ATS_PASS" if result.final_verdict == "PASS" else "ATS_FAIL",
                    "verdict": result.verdict,
                    "final_verdict": result.final_verdict,
                    "verdict_summary": result.verdict_summary,
                    "weightage": result.weightage.model_dump() if result.weightage else None,
                    "is_rerun": True,
                },
            )
    finally:
        release_ats_lock(application_id)


def ack_ats_rerun_notice(application_id: str) -> None:
    with db_cursor() as (conn, cur):
        cur.execute("UPDATE Applications SET ats_rerun_unseen = 0 WHERE id = ?", application_id)
        conn.commit()


def _fetch_ats_rerun_notice(cur, application_id: str, current_status: str, current_ats_details: str | None) -> ATSRerunNotice | None:
    cur.execute("SELECT ats_rerun_unseen FROM Applications WHERE id = ?", application_id)
    row = cur.fetchone()
    if not row or not row[0]:
        return None

    cur.execute(
        """
        SELECT TOP 1 status FROM ATSEvaluationHistory
        WHERE application_id = ? ORDER BY created_at DESC
        """,
        application_id,
    )
    hist_row = cur.fetchone()
    previous_status = str(hist_row[0]) if hist_row else None

    current_label = _VERDICT_LABELS.get(current_status, current_status)
    previous_label = _VERDICT_LABELS.get(previous_status, previous_status) if previous_status else None

    parsed = _parse_ats_details(current_ats_details)
    summary = f" {parsed.verdict_summary}" if parsed and parsed.verdict_summary else ""

    if previous_label:
        message = f"Your ATS screening was re-run by the recruiter. Previous result: {previous_label}. New result: {current_label}.{summary}"
    else:
        message = f"Your ATS screening was re-run by the recruiter. Result: {current_label}.{summary}"

    return ATSRerunNotice(previous_verdict=previous_label, new_verdict=current_label, message=message)


def apply_to_job(
    job_posting_id: str,
    candidate_id: str,
    cv_content: bytes | None = None,
    cv_filename: str | None = None,
) -> ApplyResponse:
    resume_id: str | None = None
    if cv_content:
        from app.services.cv_parser_service import parse_and_store_cv
        cv_result = parse_and_store_cv(cv_content, cv_filename, candidate_id)
        resume_id = cv_result["resume_id"]

    with db_cursor() as (conn, cur):
        # Validate the candidate profile exists (prevents recruiter from applying)
        cur.execute("SELECT id FROM CandidateProfiles WHERE id = ?", candidate_id)
        if not cur.fetchone():
            raise ValueError("Invalid candidate profile. Only candidates may apply for jobs.")

        # Validate the job exists and is currently active (not expired)
        cur.execute(
            """
            SELECT id FROM JobPostings
            WHERE id = ? AND status = 'active'
              AND (expires_at IS NULL OR CAST(expires_at AS DATE) >= CAST(GETDATE() AS DATE))
            """,
            job_posting_id,
        )
        if not cur.fetchone():
            raise ValueError("Job not found or no longer accepting applications.")

        # Check for existing application
        cur.execute(
            "SELECT id FROM Applications WHERE job_id = ? AND candidate_id = ?",
            job_posting_id,
            candidate_id,
        )
        row = cur.fetchone()

        if row:
            application_id = str(row[0])
            created = False
            if resume_id:
                cur.execute(
                    "UPDATE Applications SET resume_id = ? WHERE id = ?",
                    resume_id,
                    application_id,
                )
        else:
            application_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO Applications (id, job_id, candidate_id, resume_id, status, cover_letter, applied_at)
                VALUES (?, ?, ?, ?, 'ATS_PENDING', NULL, GETDATE())
                """,
                application_id,
                job_posting_id,
                candidate_id,
                resume_id,
            )
            created = True

        conn.commit()

        msg = "Application created, pending ATS screening." if created else "Application already exists."
        return ApplyResponse(application_id=application_id, created=created, message=msg)


def _create_interviews_for_application(cur, application_id: str, job_posting_id: str) -> None:
    """Create an Interview row for each active round of the job, if one doesn't already exist.

    Only call this once ATS has passed the application — interviews must not exist
    for applications that are ATS_PENDING or ATS_FAIL.
    """
    cur.execute(
        """
        SELECT id FROM InterviewRounds
        WHERE job_posting_id = ? AND is_active = 1
        ORDER BY round_order
        """,
        job_posting_id,
    )
    rounds = [str(r[0]) for r in cur.fetchall()]

    for round_id in rounds:
        cur.execute(
            "SELECT id FROM Interviews WHERE interview_round_id = ? AND application_id = ?",
            round_id,
            application_id,
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO Interviews
                    (id, interview_round_id, application_id, status, scheduled_at, completed_at, feedback, result)
                VALUES (?, ?, ?, 'Scheduled', GETDATE(), NULL, NULL, NULL)
                """,
                str(uuid.uuid4()),
                round_id,
                application_id,
            )


def get_interview_stages(application_id: str) -> InterviewStagesResponse:
    with db_cursor() as (conn, cur):
        # Defensive re-check: apply any rerun result that was deferred while a round was
        # In Progress and has since concluded (see apply_pending_ats_rerun) — guarantees a
        # candidate never sees a stale PASS after a recruiter's rerun has actually failed
        # them, even if the interview_service.py write-path hook was somehow missed.
        if apply_pending_ats_rerun(cur, application_id):
            conn.commit()

        # Resolve job_posting_id and ATS info from application (join for job meta)
        cur.execute(
            """
            SELECT a.job_id, a.status, a.ats_details,
                   jr.title, el.name, c.name
            FROM Applications a
            JOIN JobPostings jp ON jp.id = a.job_id
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            JOIN ExperienceLevels el ON el.id = jp.experience_level_id
            JOIN Companies c ON c.id = jp.company_id
            WHERE a.id = ?
            """,
            application_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Application {application_id} not found")
        job_posting_id = str(row[0])
        app_status = row[1]
        ats_result = _parse_ats_details(row[2])
        job_role_title: str | None = row[3]
        experience_level_name: str | None = row[4]
        company: str | None = row[5]

        # Derive ats_status from application status
        if app_status in _ATS_PASSED_STATUSES:
            ats_status = "pass"
        elif app_status in _ATS_FAILED_STATUSES:
            ats_status = "fail"
        else:
            ats_status = "pending"

        # Fetch rounds joined with interview type name and all interview detail fields
        cur.execute(
            """
            SELECT
                ir.id            AS interview_round_id,
                irt.name         AS title,
                ir.round_order,
                i.id             AS interview_id,
                i.status,
                i.feedback,
                i.result,
                i.scheduled_at,
                i.completed_at,
                (SELECT AVG(CAST(iq2.score AS FLOAT))
                 FROM InterviewQuestions iq2
                 WHERE iq2.interview_id = i.id) AS avg_score,
                (SELECT COUNT(*)
                 FROM InterviewQuestions iq3
                 WHERE iq3.interview_id = i.id AND iq3.score IS NOT NULL) AS questions_total,
                (SELECT COUNT(*)
                 FROM InterviewQuestions iq4
                 WHERE iq4.interview_id = i.id AND iq4.score >= ?) AS questions_correct
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i
                ON i.interview_round_id = ir.id
                AND i.application_id = ?
            WHERE ir.job_posting_id = ?
            ORDER BY ir.round_order
            """,
            CORRECT_ANSWER_SCORE_THRESHOLD,
            application_id,
            job_posting_id,
        )
        rows = cur.fetchall()

        rounds: list[InterviewRoundInfo] = []
        current_round_id: str | None = None

        for r in rows:
            interview_round_id = str(r[0])
            title = r[1]
            round_order = r[2]
            interview_id = str(r[3]) if r[3] else None
            status = r[4]
            feedback: str | None = r[5]
            result: str | None = r[6]
            scheduled_at: str | None = r[7].isoformat() if r[7] else None
            completed_at: str | None = r[8].isoformat() if r[8] else None
            avg_score: float | None = float(r[9]) if r[9] is not None else None
            questions_total: int | None = int(r[10]) if r[10] else None
            questions_correct: int | None = int(r[11]) if questions_total else None

            rounds.append(
                InterviewRoundInfo(
                    interview_round_id=interview_round_id,
                    interview_id=interview_id,
                    title=title,
                    round_order=round_order,
                    status=status,
                    feedback=feedback,
                    result=result,
                    scheduled_at=scheduled_at,
                    completed_at=completed_at,
                    avg_score=avg_score,
                    questions_total=questions_total,
                    questions_correct=questions_correct,
                )
            )

            # First (lowest round_order) round that is Scheduled or In Progress
            if current_round_id is None and status in ACTIVE_STATUSES:
                current_round_id = interview_round_id

        ats_rerun_notice = _fetch_ats_rerun_notice(cur, application_id, app_status, row[2])

        return InterviewStagesResponse(
            application_id=application_id,
            rounds=rounds,
            current_round_id=current_round_id,
            ats_status=ats_status,
            ats_result=ats_result,
            application_status=app_status,
            job_role_title=job_role_title,
            experience_level_name=experience_level_name,
            company=company,
            ats_rerun_notice=ats_rerun_notice,
        )


def _derive_status(app_status: str, active_interview_status: str | None) -> str:
    """Return the most meaningful status to show the candidate."""
    if app_status in ("HIRED", "REJECTED", "ATS_FAIL", "ATS_PENDING"):
        return app_status
    if active_interview_status:
        s = active_interview_status.lower()
        if s == "failed":
            return "INTERVIEW_FAILED"
        if s == "pass":
            return "INTERVIEW_PASS"
        if s == "in progress":
            return "IN_PROGRESS"
        if s == "scheduled":
            return "INTERVIEW_SCHEDULED"
    return app_status


def get_my_applications(candidate_id: str) -> list[MyApplicationItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT
                a.id, a.job_id, a.status, a.applied_at,
                jp.description, jp.location, jp.job_type, jp.salary_range,
                jr.id, jr.title,
                el.id, el.name,
                c.name,
                (
                    SELECT TOP 1 i2.status
                    FROM Interviews i2
                    JOIN InterviewRounds ir2 ON ir2.id = i2.interview_round_id
                    WHERE i2.application_id = a.id
                      AND LOWER(i2.status) IN ('scheduled', 'in progress', 'failed')
                    ORDER BY ir2.round_order ASC
                ) AS active_interview_status,
                (
                    SELECT TOP 1 irt2.name
                    FROM Interviews i2
                    JOIN InterviewRounds ir2 ON ir2.id = i2.interview_round_id
                    JOIN InterviewRoundTypes irt2 ON irt2.id = ir2.interview_round_type_id
                    WHERE i2.application_id = a.id
                      AND LOWER(i2.status) IN ('scheduled', 'in progress', 'failed')
                    ORDER BY ir2.round_order ASC
                ) AS active_interview_round_title
            FROM Applications a
            JOIN JobPostings jp ON jp.id = a.job_id
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            JOIN ExperienceLevels el ON el.id = jp.experience_level_id
            JOIN Companies c ON c.id = jp.company_id
            WHERE a.candidate_id = ?
            ORDER BY a.applied_at DESC
            """,
            candidate_id,
        )
        rows = cur.fetchall()
        return [
            MyApplicationItem(
                application_id=str(r[0]),
                job_id=str(r[1]),
                status=_derive_status(str(r[2]), str(r[13]) if r[13] else None),
                applied_at=r[3].isoformat() if r[3] else "",
                description=r[4] or "",
                location=r[5],
                job_type=r[6],
                salary_range=r[7],
                job_role_id=int(r[8]),
                job_role_title=r[9],
                experience_level_id=int(r[10]),
                experience_level_name=r[11],
                company=r[12],
                latest_interview_round_title=str(r[14]) if r[14] else None,
            )
            for r in rows
        ]


def get_interview_questions(interview_id: str) -> list[InterviewQuestionItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT q.id, q.question_text, q.question_type, q.options,
                   iq.candidate_answer, iq.score, iq.notes
            FROM InterviewQuestions iq
            JOIN Questions q ON q.id = iq.question_id
            WHERE iq.interview_id = ?
            ORDER BY q.created_at
            """,
            interview_id,
        )
        rows = cur.fetchall()
        items = []
        for r in rows:
            choices, correct_option = _parse_options(r[3])
            score = r[5]
            items.append(InterviewQuestionItem(
                question_id=str(r[0]),
                question_text=r[1],
                question_type=r[2] or "short_answer",
                options=choices,
                correct_option=correct_option,
                candidate_answer=r[4],
                score=score,
                notes=r[6],
                is_correct=(score >= CORRECT_ANSWER_SCORE_THRESHOLD) if score is not None else None,
            ))
        return items


def _fetch_application_for_ats(
    application_id: str,
) -> tuple[str, str, str, ATSCheckResponse | None, str | None]:
    """Blocking DB read — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT job_id, candidate_id, status, ats_details, resume_id FROM Applications WHERE id = ?",
            application_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Application {application_id} not found")
        job_id, candidate_id, status = str(row[0]), str(row[1]), row[2]
        cached_ats_result = _parse_ats_details(row[3])
        resume_id = str(row[4]) if row[4] else None

        parsed_text: str | None = None
        if resume_id:
            cur.execute("SELECT parsed_text FROM Resumes WHERE id = ?", resume_id)
            resume_row = cur.fetchone()
            if resume_row and resume_row[0]:
                parsed_text = str(resume_row[0])
    return job_id, candidate_id, status, cached_ats_result, parsed_text


def _create_interviews_and_commit(application_id: str, job_id: str) -> None:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        _create_interviews_for_application(cur, application_id, job_id)
        conn.commit()


def _mark_ats_error(application_id: str) -> None:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop."""
    with db_cursor() as (conn, cur):
        cur.execute("UPDATE Applications SET status = 'ATS_ERROR' WHERE id = ?", application_id)
        conn.commit()


def _persist_ats_result(
    application_id: str,
    job_id: str,
    new_status: str,
    details_json: str,
    evaluated_at: datetime,
    model_version: str,
) -> str | None:
    """Blocking DB write — run via asyncio.to_thread so it doesn't block the event loop.

    Returns the next round's Interviews.id to pre-generate questions for, if ATS passed
    and a next round exists — the caller fires the Celery trigger for it.
    """
    target_interview_id: str | None = None
    with db_cursor() as (conn, cur):
        cur.execute(
            "UPDATE Applications SET status = ?, ats_details = ?, ats_evaluated_at = ?, ats_model_version = ? WHERE id = ?",
            new_status,
            details_json,
            evaluated_at,
            model_version,
            application_id,
        )
        if new_status == "ATS_PASS":
            _create_interviews_for_application(cur, application_id, job_id)
            from app.services.interview_service import find_next_scheduled_round
            target_interview_id = find_next_scheduled_round(cur, application_id, min_round_order=0)
        conn.commit()
    return target_interview_id


async def run_ats_for_application(application_id: str) -> ATSCheckResponse:
    """Run ATS eligibility check for an application and persist the result.

    If ATS has already run (status is not ATS_PENDING), returns the cached result immediately.
    Uses parsed CV text when available; falls back to profile/skills data.
    """
    job_id, candidate_id, status, cached_ats_result, parsed_text = await asyncio.to_thread(
        _fetch_application_for_ats, application_id
    )

    # Return cached result if ATS already ran
    if status in _ATS_PASSED_STATUSES:
        await asyncio.to_thread(_create_interviews_and_commit, application_id, job_id)
        if cached_ats_result:
            return cached_ats_result
        return ATSCheckResponse(verdict="QUALIFIED", verdict_summary="Candidate passed ATS screening.", final_verdict="PASS")
    if status in _ATS_FAILED_STATUSES:
        if cached_ats_result:
            return cached_ats_result
        return ATSCheckResponse(verdict="UNDERQUALIFIED", verdict_summary="Candidate did not pass ATS screening.", final_verdict="FAIL")

    # Run the LLM-powered ATS check. Guarded by the same ats_lock a recruiter-triggered
    # rerun uses (rerun_ats_and_persist) — if a rerun is somehow dispatched for this
    # application while its first-time run is still mid-flight, the rerun will see the
    # lock held and skip cleanly rather than racing this write.
    if not acquire_ats_lock(application_id):
        logger.info("ATS: application_id=%s already has a run in progress — skipping duplicate", application_id)
        if cached_ats_result:
            return cached_ats_result
        return ATSCheckResponse(verdict="QUALIFIED", verdict_summary="ATS screening already in progress.", final_verdict=None)

    try:
        from app.ai.ai_services.ats_service import ATSValidationError, check_ats_eligibility
        try:
            result, model_version = await check_ats_eligibility(
                candidate_id, job_id, parsed_text=parsed_text, application_id=application_id
            )
        except ATSValidationError as exc:
            # Malformed LLM output must never reach the DB — leave the application at ATS_ERROR
            # (queryable/distinct from ATS_PENDING) rather than writing a bad ats_details blob or
            # flipping status to PASS/FAIL on data we don't trust.
            logger.error("ATS: validation failed for application=%s, leaving status unset: %s", application_id, exc)
            await asyncio.to_thread(_mark_ats_error, application_id)
            raise

        new_status = "ATS_PASS" if result.final_verdict == "PASS" else "ATS_FAIL"
        details_json = result.model_dump_json()
        evaluated_at = datetime.now(timezone.utc)

        target_interview_id = await asyncio.to_thread(
            _persist_ats_result, application_id, job_id, new_status, details_json, evaluated_at, model_version
        )

        if new_status == "ATS_PASS" and target_interview_id:
            from app.tasks import written_test_tasks
            written_test_tasks.trigger.delay(target_interview_id)

        await publish_ats_completed(
            application_id,
            {
                "event": "ats_completed",
                "application_id": application_id,
                "status": new_status,
                "verdict": result.verdict,
                "final_verdict": result.final_verdict,
                "verdict_summary": result.verdict_summary,
                "weightage": result.weightage.model_dump(),
            },
        )
    finally:
        release_ats_lock(application_id)

    return ATSCheckResponse(**result.model_dump())
