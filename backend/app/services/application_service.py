import json
import logging
import uuid

from pydantic import ValidationError

from app.database import get_connection
from app.schemas.applications import ATSCheckResponse, ApplyResponse, InterviewQuestionItem, InterviewRoundInfo, InterviewStagesResponse, MyApplicationItem

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("Scheduled", "In Progress")

# Application statuses that indicate ATS has already passed
_ATS_PASSED_STATUSES = ("ATS_PASS", "IN_PROGRESS", "HIRED")
_ATS_FAILED_STATUSES = ("ATS_FAIL", "REJECTED")


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

    conn = get_connection()
    try:
        cur = conn.cursor()

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
    finally:
        conn.close()


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
    conn = get_connection()
    try:
        cur = conn.cursor()

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
                 WHERE iq2.interview_id = i.id) AS avg_score
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i
                ON i.interview_round_id = ir.id
                AND i.application_id = ?
            WHERE ir.job_posting_id = ?
            ORDER BY ir.round_order
            """,
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
                )
            )

            # First (lowest round_order) round that is Scheduled or In Progress
            if current_round_id is None and status in ACTIVE_STATUSES:
                current_round_id = interview_round_id

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
        )
    finally:
        conn.close()


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
    conn = get_connection()
    try:
        cur = conn.cursor()
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
    finally:
        conn.close()


def get_interview_questions(interview_id: str) -> list[InterviewQuestionItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT q.id, q.question_text, iq.candidate_answer, iq.score, iq.notes
            FROM InterviewQuestions iq
            JOIN Questions q ON q.id = iq.question_id
            WHERE iq.interview_id = ?
            ORDER BY q.created_at
            """,
            interview_id,
        )
        rows = cur.fetchall()
        return [
            InterviewQuestionItem(
                question_id=str(r[0]),
                question_text=r[1],
                candidate_answer=r[2],
                score=r[3],
                notes=r[4],
            )
            for r in rows
        ]
    finally:
        conn.close()


async def run_ats_for_application(application_id: str) -> ATSCheckResponse:
    """Run ATS eligibility check for an application and persist the result.

    If ATS has already run (status is not ATS_PENDING), returns the cached result immediately.
    Uses parsed CV text when available; falls back to profile/skills data.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
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
    finally:
        conn.close()

    # Return cached result if ATS already ran
    if status in _ATS_PASSED_STATUSES:
        conn = get_connection()
        try:
            cur = conn.cursor()
            _create_interviews_for_application(cur, application_id, job_id)
            conn.commit()
        finally:
            conn.close()
        if cached_ats_result:
            return cached_ats_result
        return ATSCheckResponse(verdict="PASS", verdict_summary="Candidate passed ATS screening.")
    if status in _ATS_FAILED_STATUSES:
        if cached_ats_result:
            return cached_ats_result
        return ATSCheckResponse(verdict="FAIL", verdict_summary="Candidate did not pass ATS screening.")

    # Run the LLM-powered ATS check
    from app.ai.ai_services.ats_service import check_ats_eligibility
    result = await check_ats_eligibility(candidate_id, job_id, parsed_text=parsed_text)

    new_status = "ATS_PASS" if result.verdict == "PASS" else "ATS_FAIL"
    details_json = result.model_dump_json()

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE Applications SET status = ?, ats_details = ? WHERE id = ?",
            new_status,
            details_json,
            application_id,
        )
        if new_status == "ATS_PASS":
            _create_interviews_for_application(cur, application_id, job_id)
        conn.commit()
    finally:
        conn.close()

    return ATSCheckResponse(**result.model_dump())
