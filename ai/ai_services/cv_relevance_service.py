from io import BytesIO

import httpx
from pypdf import PdfReader
from sqlalchemy import select

from agents.interview_agent.models import (
    CandidateProfiles,
    CandidateSkills,
    JobRequiredSkills,
    SkillSets,
)
from agents.interview_agent.prompts import EXTRACT_RESUME_CV_RELEVANCE_SYSTEM_PROMPT
from agents.interview_agent.schemas import CandidateCVRelevance, RelevantSkill
from app.core.config import get_llm
from app.database.session import SessionLocal


async def fetch_candidate_cv_relevance(
    candidate_id: str, job_posting_id: str
) -> CandidateCVRelevance:
    """fetch_candidate_cv_relevance(): candidate skills (`CandidateSkills` +
    `SkillSets`) that overlap with the job posting's required skills
    (`JobRequiredSkills`), plus a job experience summary from
    `CandidateProfiles.bio`.

    Note: the schema has no Projects table yet, so `relevant_projects` is
    always empty for now.
    """

    with SessionLocal() as session:
        candidate = session.execute(
            select(CandidateProfiles).where(CandidateProfiles.id == candidate_id)
        ).scalar_one()

        job_skill_ids = session.execute(
            select(JobRequiredSkills.skill_id).where(
                JobRequiredSkills.job_id == job_posting_id
            )
        ).scalars().all()

        relevant_skill_rows = session.execute(
            select(
                SkillSets.name,
                CandidateSkills.proficiency_level,
                CandidateSkills.years_of_experience,
            )
            .join(SkillSets, SkillSets.id == CandidateSkills.skill_id)
            .where(
                CandidateSkills.candidate_id == candidate_id,
                CandidateSkills.skill_id.in_(job_skill_ids),
            )
        ).all()

    return CandidateCVRelevance(
        job_experience_summary=candidate.bio or "",
        relevant_skills=[
            RelevantSkill(
                skill_name=name,
                proficiency_level=proficiency_level,
                years_of_experience=years_of_experience,
            )
            for name, proficiency_level, years_of_experience in relevant_skill_rows
        ],
        relevant_projects=[],
    )


async def _extract_resume_text(resume_url: str) -> str:
    """Download the candidate's resume PDF and extract its raw text."""

    async with httpx.AsyncClient() as client:
        response = await client.get(resume_url)
        response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


async def fetch_candidate_cv_relevance_2(candidate_id: str) -> CandidateCVRelevance:
    """fetch_candidate_cv_relevance_2(): alternative to
    fetch_candidate_cv_relevance() that parses the candidate's resume PDF
    (`CandidateProfiles.resume_url`) directly via an LLM, instead of relying on
    `CandidateSkills` / `JobRequiredSkills`.

    Unlike fetch_candidate_cv_relevance(), this can populate
    `relevant_projects` since it reads straight from the resume content.
    """

    with SessionLocal() as session:
        candidate = session.execute(
            select(CandidateProfiles).where(CandidateProfiles.id == candidate_id)
        ).scalar_one()

    resume_text = await _extract_resume_text(candidate.resume_url)

    structured_llm = get_llm().with_structured_output(CandidateCVRelevance)

    return await structured_llm.ainvoke(
        [
            ("system", EXTRACT_RESUME_CV_RELEVANCE_SYSTEM_PROMPT),
            ("user", resume_text),
        ]
    )
