from dataclasses import dataclass

from sqlalchemy import func, select

from agents.interview_agent.models import (
    ExperienceLevels,
    InterviewRoundTypes,
    JobRoles,
    Questions,
)
from agents.interview_agent.schemas import FetchQuestionsFromDBOutput, QuestionItem
from app.database.session import SessionLocal


async def fetch_questions_from_db(
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
    limit: int = 20,
) -> FetchQuestionsFromDBOutput:
    """fetch_questions_from_db(): random sample of active questions from
    `Questions`, scoped to the given round type, job role, and experience
    level."""

    stmt = (
        select(Questions.question_text)
        .where(
            Questions.interview_round_type_id == interview_round_type_id,
            Questions.job_role_id == job_role_id,
            Questions.experience_level_id == experience_level_id,
            Questions.is_active == True,
        )
        .order_by(func.newid())
        .limit(limit)
    )

    with SessionLocal() as session:
        rows = session.execute(stmt).scalars().all()

    return FetchQuestionsFromDBOutput(
        questions=[QuestionItem(question_text=text) for text in rows]
    )


@dataclass
class InterviewContext:
    job_role_title: str
    job_role_category: str
    experience_level_name: str
    round_type_name: str


async def fetch_interview_context(
    interview_round_type_id: int,
    job_role_id: int,
    experience_level_id: int,
) -> InterviewContext:
    """Resolve the lookup ids carried in AgentState (`JobRoles`,
    `ExperienceLevels`, `InterviewRoundTypes`) to human-readable labels for
    the generate_questions() prompt."""

    with SessionLocal() as session:
        job_role = session.execute(
            select(JobRoles).where(JobRoles.id == job_role_id)
        ).scalar_one()
        experience_level = session.execute(
            select(ExperienceLevels).where(ExperienceLevels.id == experience_level_id)
        ).scalar_one()
        round_type = session.execute(
            select(InterviewRoundTypes).where(
                InterviewRoundTypes.id == interview_round_type_id
            )
        ).scalar_one()

    return InterviewContext(
        job_role_title=job_role.title,
        job_role_category=job_role.category,
        experience_level_name=experience_level.name,
        round_type_name=round_type.name,
    )
