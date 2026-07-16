from dataclasses import dataclass, field

from app.database import db_cursor
from app.ai.interview_tools.schemas import FetchQuestionsFromDBOutput, QuestionItem


async def fetch_questions_from_db(
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    limit: int = 20,
) -> FetchQuestionsFromDBOutput:
    """Random sample of active questions from Questions, scoped to the given
    round type, job role, and experience level."""

    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT TOP (?) question_text
            FROM Questions
            WHERE interview_round_type_id = ?
              AND job_role_id = ?
              AND experience_level_id = ?
              AND is_active = 1
            ORDER BY NEWID()
            """,
            limit,
            interview_round_type_id,
            job_role_id,
            experience_level_id,
        )
        rows = cur.fetchall()

    return FetchQuestionsFromDBOutput(
        questions=[QuestionItem(question_text=row[0]) for row in rows]
    )


@dataclass
class InterviewContext:
    job_role_title: str
    job_role_category: str
    experience_level_name: str
    round_type_name: str
    job_description: str = ""
    required_skills: list[str] = field(default_factory=list)


async def fetch_interview_context(
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    job_posting_id: str | None = None,
) -> InterviewContext:
    """Resolve lookup ids to human-readable labels for the generate_questions() prompt.

    When `job_posting_id` is given, also fetches the job posting's description and
    required skills (JobRequiredSkills -> SkillSets) — same query shape as
    job_post_service.fetch_job_post_data, reused here for the written-test prompt.
    """

    with db_cursor() as (conn, cur):
        cur.execute("SELECT title, category FROM JobRoles WHERE id = ?", job_role_id)
        job_role = cur.fetchone()

        cur.execute("SELECT name FROM ExperienceLevels WHERE id = ?", experience_level_id)
        exp_level = cur.fetchone()

        cur.execute("SELECT name FROM InterviewRoundTypes WHERE id = ?", interview_round_type_id)
        round_type = cur.fetchone()

        job_description = ""
        required_skills: list[str] = []
        if job_posting_id:
            cur.execute("SELECT description FROM JobPostings WHERE id = ?", job_posting_id)
            jp_row = cur.fetchone()
            job_description = (jp_row[0] or "") if jp_row else ""

            cur.execute(
                """
                SELECT ss.name
                FROM JobRequiredSkills jrs
                JOIN SkillSets ss ON ss.id = jrs.skill_id
                WHERE jrs.job_id = ?
                """,
                job_posting_id,
            )
            required_skills = [r[0] for r in cur.fetchall()]

    return InterviewContext(
        job_role_title=job_role[0],
        job_role_category=job_role[1],
        experience_level_name=exp_level[0],
        round_type_name=round_type[0],
        job_description=job_description,
        required_skills=required_skills,
    )
