from app.database import get_connection


async def fetch_candidate_cv_relevance(application_id: str) -> str:
    """Return the parsed CV text for the resume attached to the given application.

    Queries Applications for resume_id, then Resumes for parsed_text.
    Returns an empty string if no resume is attached or parsed_text is NULL.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT resume_id FROM Applications WHERE id = ?",
            application_id,
        )
        row = cur.fetchone()
        resume_id = row[0] if row else None

        if not resume_id:
            return ""

        cur.execute(
            "SELECT parsed_text FROM Resumes WHERE id = ?",
            resume_id,
        )
        resume_row = cur.fetchone()
        parsed_text = resume_row[0] if resume_row else None
    finally:
        conn.close()

    return parsed_text or ""


# ---------------------------------------------------------------------------
# Commented-out: pre-CV-upload flow (replaced by fetch_candidate_cv_relevance above)
# ---------------------------------------------------------------------------

# from io import BytesIO
# import httpx
# from pypdf import PdfReader
# from app.ai.interview_tools.prompts import EXTRACT_RESUME_CV_RELEVANCE_SYSTEM_PROMPT
# from app.ai.interview_tools.schemas import CandidateCVRelevance, RelevantSkill
# from app.core.config import get_llm
#
#
# async def fetch_candidate_cv_relevance(
#     candidate_id: str, job_posting_id: str
# ) -> CandidateCVRelevance:
#     """Candidate skills (CandidateSkills + SkillSets) that overlap with the
#     job posting's required skills (JobRequiredSkills), plus bio as the
#     job experience summary."""
#
#     conn = get_connection()
#     try:
#         cur = conn.cursor()
#         cur.execute("SELECT bio FROM CandidateProfiles WHERE id = ?", candidate_id)
#         candidate_row = cur.fetchone()
#         bio = candidate_row[0] if candidate_row else ""
#         cur.execute(
#             "SELECT skill_id FROM JobRequiredSkills WHERE job_id = ?",
#             job_posting_id,
#         )
#         job_skill_ids = [row[0] for row in cur.fetchall()]
#         if job_skill_ids:
#             placeholders = ",".join("?" * len(job_skill_ids))
#             cur.execute(
#                 f"""
#                 SELECT ss.name, cs.proficiency_level, cs.years_of_experience
#                 FROM CandidateSkills cs
#                 JOIN SkillSets ss ON ss.id = cs.skill_id
#                 WHERE cs.candidate_id = ?
#                   AND cs.skill_id IN ({placeholders})
#                 """,
#                 candidate_id,
#                 *job_skill_ids,
#             )
#             skill_rows = cur.fetchall()
#         else:
#             skill_rows = []
#     finally:
#         conn.close()
#     return CandidateCVRelevance(
#         job_experience_summary=bio or "",
#         relevant_skills=[
#             RelevantSkill(
#                 skill_name=name,
#                 proficiency_level=proficiency_level,
#                 years_of_experience=years_of_experience,
#             )
#             for name, proficiency_level, years_of_experience in skill_rows
#         ],
#         relevant_projects=[],
#     )
#
#
# async def _extract_resume_text(resume_url: str) -> str:
#     async with httpx.AsyncClient() as client:
#         response = await client.get(resume_url)
#         response.raise_for_status()
#     reader = PdfReader(BytesIO(response.content))
#     return "\n".join(page.extract_text() or "" for page in reader.pages)
#
#
# async def fetch_candidate_cv_relevance_2(candidate_id: str) -> CandidateCVRelevance:
#     conn = get_connection()
#     try:
#         cur = conn.cursor()
#         cur.execute("SELECT resume_url FROM CandidateProfiles WHERE id = ?", candidate_id)
#         row = cur.fetchone()
#         resume_url = row[0] if row else None
#     finally:
#         conn.close()
#     resume_text = await _extract_resume_text(resume_url)
#     structured_llm = get_llm().with_structured_output(CandidateCVRelevance)
#     return await structured_llm.ainvoke(
#         [
#             ("system", EXTRACT_RESUME_CV_RELEVANCE_SYSTEM_PROMPT),
#             ("user", resume_text),
#         ]
#     )
