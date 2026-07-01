import uuid

from app.database import get_connection
from app.schemas.jobs import (
    CandidateInfo,
    CandidatePanelResponse,
    CandidateSkillItem,
    EvaluationQuestionItem,
    InterviewProgressItem,
    InterviewRoundTypeItem,
    JobInterviewRoundItem,
    JobListItem,
    JobPostRequest,
    JobPostResponse,
    JobStatsResponse,
    JobStatsRound,
    RoundCandidateItem,
)


def get_job_rounds(job_id: str) -> list[JobInterviewRoundItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ir.round_order, irt.name, ir.failing_criteria, ir.description
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            WHERE ir.job_posting_id = ? AND ir.is_active = 1
            ORDER BY ir.round_order
            """,
            job_id,
        )
        return [
            JobInterviewRoundItem(
                round_order=int(row[0]),
                round_type_name=str(row[1]),
                failing_criteria=int(row[2]) if row[2] is not None else None,
                description=str(row[3]) if row[3] else None,
            )
            for row in cur.fetchall()
        ]
    finally:
        conn.close()


def _escape_like(value: str) -> str:
    """Escape SQL Server LIKE special characters so user input is treated literally."""
    return value.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def list_interview_round_types() -> list[InterviewRoundTypeItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description FROM InterviewRoundTypes ORDER BY id")
        return [
            InterviewRoundTypeItem(id=int(row[0]), name=str(row[1]), description=str(row[2]) if row[2] else None)
            for row in cur.fetchall()
        ]
    finally:
        conn.close()


def post_job(data: JobPostRequest) -> JobPostResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT company_id FROM RecruiterProfiles WHERE id = ?", data.recruiter_id)
        row = cur.fetchone()
        if not row:
            raise ValueError("Recruiter profile not found.")
        company_id = str(row[0])

        job_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO JobPostings
                (id, recruiter_id, company_id, job_role_id, experience_level_id, description,
                 location, job_type, salary_range, status, posted_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', GETDATE(), ?)
            """,
            job_id,
            data.recruiter_id,
            company_id,
            data.job_role_id,
            data.experience_level_id,
            data.description,
            data.location,
            data.job_type,
            data.salary_range,
            data.expires_at,
        )

        for skill_id in data.skill_ids:
            cur.execute(
                """
                INSERT INTO JobRequiredSkills (id, job_id, skill_id, proficiency_level, is_mandatory)
                VALUES (?, ?, ?, 'Intermediate', 1)
                """,
                str(uuid.uuid4()),
                job_id,
                skill_id,
            )

        for round_input in data.interview_rounds:
            round_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO InterviewRounds
                    (id, job_posting_id, interview_round_type_id, round_order,
                     description, failing_criteria, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                round_id,
                job_id,
                round_input.round_type_id,
                round_input.round_order,
                round_input.description,
                round_input.failing_criteria,
            )

        conn.commit()
        return JobPostResponse(job_id=job_id, message="Job posted successfully.")
    finally:
        conn.close()


def _row_to_job(row) -> JobListItem:
    skills_raw = row[9]
    required_skills = [s.strip() for s in skills_raw.split(',') if s.strip()] if skills_raw else []
    return JobListItem(
        id=str(row[0]),
        description=str(row[1]),
        company=str(row[2]),
        job_role_title=str(row[3]),
        location=str(row[4]),
        job_type=str(row[5]),
        salary_range=str(row[6]) if row[6] else None,
        posted_at=str(row[7]),
        expires_at=str(row[8]) if row[8] else None,
        required_skills=required_skills,
        job_role_id=int(row[10]),
        experience_level_name=str(row[11]),
        experience_level_id=int(row[12]),
        status=str(row[13]) if row[13] else 'active',
    )


_JOB_SELECT = """
    SELECT jp.id, jp.description, c.name, jr.title,
           jp.location, jp.job_type, jp.salary_range,
           CONVERT(varchar, jp.posted_at, 127),
           CONVERT(varchar, jp.expires_at, 127),
           STRING_AGG(s.name, ',') WITHIN GROUP (ORDER BY s.name),
           jp.job_role_id, el.name, jp.experience_level_id,
           jp.status
    FROM JobPostings jp
    JOIN Companies c ON c.id = jp.company_id
    JOIN JobRoles jr ON jr.id = jp.job_role_id
    JOIN ExperienceLevels el ON el.id = jp.experience_level_id
    LEFT JOIN JobRequiredSkills jrs ON jrs.job_id = jp.id
    LEFT JOIN SkillSets s ON s.id = jrs.skill_id
"""

_JOB_GROUP_BY = """
    GROUP BY jp.id, jp.description, c.name, jr.title,
             jp.location, jp.job_type, jp.salary_range, jp.posted_at, jp.expires_at,
             jp.job_role_id, el.name, jp.experience_level_id, jp.status
"""


def list_jobs(
    job_role_id: int | None = None,
    experience_level_id: int | None = None,
    location: str | None = None,
    job_type: str | None = None,
    salary_range: str | None = None,
    candidate_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[JobListItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()

        conditions = [
            "jp.status = 'active'",
            "(jp.expires_at IS NULL OR CAST(jp.expires_at AS DATE) >= CAST(GETDATE() AS DATE))",
        ]
        params: list = []

        location = (location or "").strip() or None
        salary_range = (salary_range or "").strip() or None
        candidate_id = (candidate_id or "").strip() or None

        if job_role_id is not None:
            conditions.append("jp.job_role_id = ?")
            params.append(job_role_id)
        if experience_level_id is not None:
            conditions.append("jp.experience_level_id = ?")
            params.append(experience_level_id)
        if location:
            conditions.append("jp.location LIKE ?")
            params.append(f"%{_escape_like(location)}%")
        if job_type:
            conditions.append("jp.job_type = ?")
            params.append(job_type)
        if salary_range:
            conditions.append("jp.salary_range LIKE ?")
            params.append(f"%{_escape_like(salary_range)}%")
        if candidate_id:
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM Applications a WHERE a.job_id = jp.id AND a.candidate_id = ?)"
            )
            params.append(candidate_id)

        where_clause = "WHERE " + " AND ".join(conditions) + " "
        params.extend([offset, limit])

        sql = (
            _JOB_SELECT
            + where_clause
            + _JOB_GROUP_BY
            + "ORDER BY jp.posted_at DESC "
            + "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )

        cur.execute(sql, *params)
        return [_row_to_job(row) for row in cur.fetchall()]
    finally:
        conn.close()


def list_recruiter_jobs(recruiter_id: str) -> list[JobListItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            _JOB_SELECT
            + "WHERE jp.recruiter_id = ?"
            + _JOB_GROUP_BY
            + "ORDER BY jp.posted_at DESC",
            recruiter_id,
        )
        return [_row_to_job(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_job_stats(job_id: str) -> JobStatsResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT jr.title, jp.description, jp.status
            FROM JobPostings jp
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            WHERE jp.id = ?
            """,
            job_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Job not found")
        job_title, description, status = str(row[0]), str(row[1]), str(row[2])

        cur.execute(
            "SELECT s.name FROM JobRequiredSkills jrs JOIN SkillSets s ON s.id = jrs.skill_id WHERE jrs.job_id = ?",
            job_id,
        )
        required_skills = [str(r[0]) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ir.round_order, irt.name, ir.failing_criteria,
                   COUNT(DISTINCT i.application_id) AS cnt
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i ON i.interview_round_id = ir.id
            WHERE ir.job_posting_id = ? AND ir.is_active = 1
            GROUP BY ir.round_order, irt.name, ir.failing_criteria
            ORDER BY ir.round_order
            """,
            job_id,
        )
        rounds = [
            JobStatsRound(
                round_order=int(r[0]),
                round_type_name=str(r[1]),
                failing_criteria=int(r[2]) if r[2] is not None else None,
                applicants_count=int(r[3]),
            )
            for r in cur.fetchall()
        ]

        cur.execute("SELECT COUNT(*) FROM Applications WHERE job_id = ?", job_id)
        total_applicants = int(cur.fetchone()[0])

        cur.execute(
            """
            WITH RoundCount AS (
                SELECT COUNT(*) AS cnt
                FROM InterviewRounds
                WHERE job_posting_id = ? AND is_active = 1
            ),
            PassedPerApp AS (
                SELECT i.application_id, COUNT(DISTINCT i.interview_round_id) AS passed
                FROM Interviews i
                JOIN InterviewRounds ir ON ir.id = i.interview_round_id
                WHERE ir.job_posting_id = ? AND i.status = 'Pass'
                GROUP BY i.application_id
            )
            SELECT COUNT(*)
            FROM PassedPerApp p
            CROSS JOIN RoundCount r
            WHERE p.passed = r.cnt AND r.cnt > 0
            """,
            job_id,
            job_id,
        )
        passed_all_rounds = int(cur.fetchone()[0])

        cur.execute("SELECT COUNT(*) FROM Applications WHERE job_id = ? AND status = 'HIRED'", job_id)
        hired_count = int(cur.fetchone()[0])

        return JobStatsResponse(
            job_title=job_title,
            description=description,
            status=status,
            required_skills=required_skills,
            rounds=rounds,
            total_applicants=total_applicants,
            passed_all_rounds=passed_all_rounds,
            hired_count=hired_count,
        )
    finally:
        conn.close()


def get_round_candidates(job_id: str, round_order: int) -> list[RoundCandidateItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cp.id, a.id, i.id,
                   u.first_name + ' ' + u.last_name,
                   i.status
            FROM InterviewRounds ir
            JOIN Interviews i ON i.interview_round_id = ir.id
            JOIN Applications a ON a.id = i.application_id
            JOIN CandidateProfiles cp ON cp.id = a.candidate_id
            JOIN Users u ON u.id = cp.user_id
            WHERE ir.job_posting_id = ? AND ir.round_order = ? AND ir.is_active = 1
            ORDER BY u.first_name, u.last_name
            """,
            job_id,
            round_order,
        )
        return [
            RoundCandidateItem(
                candidate_id=str(r[0]),
                application_id=str(r[1]),
                interview_id=str(r[2]),
                name=str(r[3]),
                status=str(r[4]),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def get_candidate_panel(application_id: str, interview_id: str) -> CandidatePanelResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT u.first_name, u.last_name, u.email, cp.bio, cp.current_location,
                   el.name, jr.title, cp.id, u.phone, cp.linkedin_url,
                   el.min_years, el.max_years
            FROM Applications a
            JOIN CandidateProfiles cp ON cp.id = a.candidate_id
            JOIN Users u ON u.id = cp.user_id
            LEFT JOIN ExperienceLevels el ON el.id = cp.experience_level_id
            LEFT JOIN JobRoles jr ON jr.id = cp.job_role_id
            WHERE a.id = ?
            """,
            application_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Application not found")
        first_name = str(row[0])
        last_name = str(row[1])
        email = str(row[2])
        bio = str(row[3]) if row[3] else None
        current_location = str(row[4]) if row[4] else None
        experience_level = str(row[5]) if row[5] else None
        job_role = str(row[6]) if row[6] else None
        candidate_id = str(row[7])
        phone = str(row[8]) if row[8] else None
        linkedin_url = str(row[9]) if row[9] else None
        experience_years_min = int(row[10]) if row[10] is not None else None
        experience_years_max = int(row[11]) if row[11] is not None else None

        cur.execute(
            """
            SELECT s.name, cs.proficiency_level
            FROM CandidateSkills cs
            JOIN SkillSets s ON s.id = cs.skill_id
            WHERE cs.candidate_id = ?
            ORDER BY s.name
            """,
            candidate_id,
        )
        skills = [
            CandidateSkillItem(name=str(r[0]), proficiency_level=str(r[1]) if r[1] else None)
            for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT ir.round_order, irt.name, i.status, i.result,
                   CONVERT(varchar, i.completed_at, 127), i.id
            FROM Applications a
            JOIN InterviewRounds ir ON ir.job_posting_id = a.job_id
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i ON i.interview_round_id = ir.id AND i.application_id = a.id
            WHERE a.id = ? AND ir.is_active = 1
            ORDER BY ir.round_order
            """,
            application_id,
        )
        progress = [
            InterviewProgressItem(
                round_order=int(r[0]),
                round_type_name=str(r[1]),
                status=str(r[2]) if r[2] else None,
                result=float(r[3]) if r[3] is not None else None,
                completed_at=str(r[4]) if r[4] else None,
                interview_id=str(r[5]) if r[5] else None,
            )
            for r in cur.fetchall()
        ]

        cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
        iv_row = cur.fetchone()
        iv_status = str(iv_row[0]) if iv_row else None

        evaluation = None
        if iv_status in ('Pass', 'Failed'):
            cur.execute(
                """
                SELECT q.question_text, iq.candidate_answer, iq.score, iq.notes
                FROM InterviewQuestions iq
                JOIN Questions q ON q.id = iq.question_id
                WHERE iq.interview_id = ?
                ORDER BY q.created_at
                """,
                interview_id,
            )
            evaluation = [
                EvaluationQuestionItem(
                    question_text=str(r[0]),
                    candidate_answer=str(r[1]) if r[1] else None,
                    score=int(r[2]) if r[2] is not None else None,
                    notes=str(r[3]) if r[3] else None,
                )
                for r in cur.fetchall()
            ]

        return CandidatePanelResponse(
            candidate=CandidateInfo(
                first_name=first_name,
                last_name=last_name,
                email=email,
                bio=bio,
                current_location=current_location,
                experience_level=experience_level,
                job_role=job_role,
                skills=skills,
                phone=phone,
                linkedin_url=linkedin_url,
                experience_years_min=experience_years_min,
                experience_years_max=experience_years_max,
            ),
            progress=progress,
            evaluation=evaluation,
        )
    finally:
        conn.close()


def get_interview_qa(interview_id: str) -> list[EvaluationQuestionItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT q.question_text, iq.candidate_answer, iq.score, iq.notes
            FROM InterviewQuestions iq
            JOIN Questions q ON q.id = iq.question_id
            WHERE iq.interview_id = ?
            ORDER BY q.created_at
            """,
            interview_id,
        )
        return [
            EvaluationQuestionItem(
                question_text=str(r[0]),
                candidate_answer=str(r[1]) if r[1] else None,
                score=int(r[2]) if r[2] is not None else None,
                notes=str(r[3]) if r[3] else None,
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
