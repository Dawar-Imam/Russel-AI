import uuid

from app.database import get_connection
from app.schemas.applications import ApplyResponse, InterviewRoundInfo, InterviewStagesResponse

ACTIVE_STATUSES = ("Scheduled", "In Progress")


def apply_to_job(job_posting_id: str, candidate_id: str) -> ApplyResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

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
        else:
            application_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO Applications (id, job_id, candidate_id, status, cover_letter, applied_at)
                VALUES (?, ?, ?, 'Applied', NULL, GETDATE())
                """,
                application_id,
                job_posting_id,
                candidate_id,
            )
            created = True

        # Fetch all interview rounds for this job (ordered by round_order)
        cur.execute(
            """
            SELECT id FROM InterviewRounds
            WHERE job_posting_id = ? AND is_active = 1
            ORDER BY round_order
            """,
            job_posting_id,
        )
        rounds = [str(r[0]) for r in cur.fetchall()]

        # Create Interview row for each round if one doesn't exist
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

        conn.commit()

        msg = "Application created and interviews scheduled." if created else "Application already exists."
        return ApplyResponse(application_id=application_id, created=created, message=msg)
    finally:
        conn.close()


def get_interview_stages(application_id: str) -> InterviewStagesResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Resolve job_posting_id from application
        cur.execute("SELECT job_id FROM Applications WHERE id = ?", application_id)
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Application {application_id} not found")
        job_posting_id = str(row[0])

        # Fetch rounds joined with interview type name and interview status
        cur.execute(
            """
            SELECT
                ir.id            AS interview_round_id,
                irt.name         AS title,
                ir.round_order,
                i.id             AS interview_id,
                i.status
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

            rounds.append(
                InterviewRoundInfo(
                    interview_round_id=interview_round_id,
                    interview_id=interview_id,
                    title=title,
                    round_order=round_order,
                    status=status,
                )
            )

            # First (lowest round_order) round that is Scheduled or In Progress
            if current_round_id is None and status in ACTIVE_STATUSES:
                current_round_id = interview_round_id

        return InterviewStagesResponse(
            application_id=application_id,
            rounds=rounds,
            current_round_id=current_round_id,
        )
    finally:
        conn.close()
