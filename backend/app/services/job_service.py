import uuid

from app.database import get_connection
from app.schemas.jobs import JobListItem, JobPostRequest, JobPostResponse


def _escape_like(value: str) -> str:
    """Escape SQL Server LIKE special characters so user input is treated literally."""
    return value.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


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
    )


_JOB_SELECT = """
    SELECT jp.id, jp.description, c.name, jr.title,
           jp.location, jp.job_type, jp.salary_range,
           CONVERT(varchar, jp.posted_at, 127),
           CONVERT(varchar, jp.expires_at, 127),
           STRING_AGG(s.name, ',') WITHIN GROUP (ORDER BY s.name),
           jp.job_role_id, el.name, jp.experience_level_id
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
             jp.job_role_id, el.name, jp.experience_level_id
"""


def list_jobs(
    job_role_id: int | None = None,
    experience_level_id: int | None = None,
    location: str | None = None,
    job_type: str | None = None,
    salary_range: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[JobListItem]:
    conn = get_connection()
    try:
        cur = conn.cursor()

        conditions = [
            "jp.status = 'active'",
            "(jp.expires_at IS NULL OR jp.expires_at > GETDATE())",
        ]
        params: list = []

        location = (location or "").strip() or None
        salary_range = (salary_range or "").strip() or None

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
