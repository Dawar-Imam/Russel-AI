import json

from app.database import get_connection


async def fetch_job_post_data(job_posting_id: str, job_role_id: int) -> str:
    """Return JSON text describing the job posting, for the voice agent to ask relevant questions.

    Pulls: JobRoles.title/category, ExperienceLevels.name, JobPostings.description,
    and required skills (JobRequiredSkills -> SkillSets) for the given job posting.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                jp.description,
                jr.title,
                jr.category,
                el.name AS experience_level
            FROM JobPostings jp
            JOIN JobRoles jr          ON jr.id = jp.job_role_id
            JOIN ExperienceLevels el  ON el.id = jp.experience_level_id
            WHERE jp.id = ? AND jr.id = ?
            """,
            job_posting_id,
            job_role_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Job posting {job_posting_id} not found")

        description, title, category, experience_level = row

        cur.execute(
            """
            SELECT ss.name
            FROM JobRequiredSkills jrs
            JOIN SkillSets ss ON ss.id = jrs.skill_id
            WHERE jrs.job_id = ?
            """,
            job_posting_id,
        )
        skills = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    return json.dumps(
        {
            "title": title,
            "category": category,
            "experience_level": experience_level,
            "description": description,
            "required_skills": skills,
        }
    )
