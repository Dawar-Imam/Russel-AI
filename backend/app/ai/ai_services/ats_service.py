from pydantic import BaseModel

from app.core.config import get_llm
from app.database import get_connection


class ATSCheckResult(BaseModel):
    eligible: bool
    reason: str


_SYSTEM_PROMPT = """You are an ATS (Applicant Tracking System) eligibility checker.
Given a candidate profile and a job posting, determine if the candidate is a reasonable match.

Respond ONLY with a JSON object in exactly this format:
{"eligible": true, "reason": "short explanation"}
or
{"eligible": false, "reason": "short explanation"}

Rules:
- Keep reason under 150 characters and be specific about what matches or is missing.
- Be lenient — mark eligible unless there is a clear and significant skills or role mismatch.
- If information is sparse, lean toward eligible."""


async def check_ats_eligibility(candidate_id: str, job_posting_id: str) -> ATSCheckResult:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT cp.bio, el.name, jr.title
            FROM CandidateProfiles cp
            LEFT JOIN ExperienceLevels el ON el.id = cp.experience_level_id
            LEFT JOIN JobRoles jr ON jr.id = cp.job_role_id
            WHERE cp.id = ?
            """,
            candidate_id,
        )
        candidate_row = cur.fetchone()
        if not candidate_row:
            return ATSCheckResult(eligible=True, reason="Candidate profile not found; proceeding.")

        candidate_bio, experience_level, candidate_role = candidate_row

        cur.execute(
            """
            SELECT ss.name
            FROM CandidateSkills cs
            JOIN SkillSets ss ON ss.id = cs.skill_id
            WHERE cs.candidate_id = ?
            """,
            candidate_id,
        )
        candidate_skills = [r[0] for r in cur.fetchall()]

        cur.execute(
            """
            SELECT el.name, jr.title, jp.description
            FROM JobPostings jp
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            JOIN ExperienceLevels el ON el.id = jp.experience_level_id
            WHERE jp.id = ?
            """,
            job_posting_id,
        )
        job_row = cur.fetchone()
        if not job_row:
            return ATSCheckResult(eligible=True, reason="Job not found; proceeding.")

        experience_level_name, job_role, job_description = job_row
        designation = f"{experience_level_name} {job_role}"

        cur.execute(
            """
            SELECT ss.name, jrs.proficiency_level, jrs.is_mandatory
            FROM JobRequiredSkills jrs
            JOIN SkillSets ss ON ss.id = jrs.skill_id
            WHERE jrs.job_id = ?
            """,
            job_posting_id,
        )
        required_skills_rows = cur.fetchall()
    finally:
        conn.close()

    candidate_skills_str = ", ".join(candidate_skills) if candidate_skills else "Not specified"
    required_skills_str = (
        ", ".join(
            f"{name} ({level or 'any level'}){' [required]' if mandatory else ''}"
            for name, level, mandatory in required_skills_rows
        )
        if required_skills_rows
        else "Not specified"
    )

    user_message = f"""Candidate Profile:
- Background: {candidate_bio or 'Not provided'}
- Experience Level: {experience_level or 'Not specified'}
- Current Role: {candidate_role or 'Not specified'}
- Skills: {candidate_skills_str}

Job Posting:
- Title: {designation}
- Role: {job_role}
- Description: {(job_description or '')[:600]}
- Required Skills: {required_skills_str}

Is this candidate eligible for this job?"""

    structured_llm = get_llm().with_structured_output(ATSCheckResult)
    try:
        result = await structured_llm.ainvoke(
            [
                ("system", _SYSTEM_PROMPT),
                ("user", user_message),
            ]
        )
        return result
    except Exception:
        return ATSCheckResult(eligible=True, reason="Eligibility check unavailable; you may proceed.")
