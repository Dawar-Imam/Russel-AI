import logging

from pydantic import BaseModel, Field

from app.core.config import get_llm
from app.database import get_connection

logger = logging.getLogger(__name__)


class ATSCheckResult(BaseModel):
    eligible: bool
    reason: str
    role_assessment: str = Field(description="How well the candidate's role/title fits the job role, with reasoning.")
    experience_assessment: str = Field(
        description="Whether the candidate is under-, appropriately, or over-experienced for the role's "
        "required level, with reasoning based on years/seniority evidenced in the CV or profile."
    )
    skills_matched: list[str] = Field(
        default_factory=list,
        description="Required or relevant skills the candidate has evidence for (direct, equivalent, or "
        "transferable), found anywhere in the CV/profile.",
    )
    skills_missing: list[str] = Field(
        default_factory=list,
        description="Required skills with NO evidence anywhere in the CV/profile — direct, equivalent, or "
        "transferable.",
    )
    projects_assessment: str = Field(
        default="", description="Relevance of the candidate's past projects/work experience to this job's responsibilities."
    )


_SYSTEM_PROMPT = """You are an experienced technical recruiter acting as an ATS (Applicant Tracking
System) eligibility checker. You reason about evidence like a human recruiter would — you do not do
keyword or exact-string matching, except where explicitly told to be strict below.

Given a candidate's CV/profile and a job posting, evaluate four things. Two very different reasoning
modes apply — do not mix them up:

============================================================
A. SKILLS — STRICT SEMANTIC + CAPABILITY-BASED REASONING (flexible but disciplined)
============================================================

Your goal is NOT to check whether a keyword exists.
Your goal is to determine whether the candidate can realistically perform the skill using ANY evidence in the CV.

You must evaluate SKILLS as demonstrated capabilities, not tool names.

You are explicitly forbidden from:
- Splitting a capability into multiple tools as separate missing skills
- Treating adjacent tooling as unrelated skills
- Marking a skill missing if the underlying capability is clearly demonstrated
- Relying on exact keyword overlap between job skill and CV text

------------------------------------------------------------
1. Evidence source rule (VERY IMPORTANT)
------------------------------------------------------------
A skill can be satisfied using evidence from ANY of:
- Projects
- Work experience
- Internships
- Responsibilities
- Achievements
- Tools used in context
- Descriptions of testing/engineering workflows

The "Skills" section is OPTIONAL and has LOW priority.

------------------------------------------------------------
2. Capability-first reasoning rule
------------------------------------------------------------
Always convert a required skill into a "capability intent".

Example:
- "API Testing" = ability to validate APIs, test endpoints, verify responses
- "Bug Reporting" = ability to document defects clearly and track issues
- "SQL" = ability to query relational databases
- "JIRA" = ability to track issues/bugs in a project tracking system

Then search CV for ANY evidence of that capability.

------------------------------------------------------------
3. Equivalent Match rule (STRICT but real-world aware)
------------------------------------------------------------
Treat as Equivalent ONLY when the underlying capability is the same:

Examples (valid equivalence):
- MySQL, PostgreSQL, SQLite → SQL
- Postman, REST client usage, Swagger testing → API Testing
- Trello, Jira, Azure DevOps Boards → Issue Tracking / Bug Tracking
- Bug reporting, defect logging, issue documentation → Bug Reporting

IMPORTANT:
Do NOT require tool-to-tool identity.
Do NOT treat absence of the exact tool name as a mismatch if capability exists.

------------------------------------------------------------
4. Transferable Match rule (must be grounded in evidence)
------------------------------------------------------------
Only use Transferable Match when:
- Candidate clearly performed a related task
- Or demonstrated partial execution of the skill

Example:
- “tested endpoints manually in a project” → Transferable for API Testing
- “maintained test cases and reported issues in spreadsheet” → Transferable for Jira/Bug Tracking

------------------------------------------------------------
5. CRITICAL ANTI-ERROR RULE (fixes your current issue)
------------------------------------------------------------
NEVER mark a skill as Missing if:
- The candidate has demonstrated the underlying testing / engineering workflow
  even if the tool name is different or absent.

Example:
If CV says:
- “used Postman to validate endpoints”

Then:
- API Testing = PRESENT (Equivalent Match)
NOT Missing

If CV says:
- “logged defects in project documentation / spreadsheets”

Then:
- Bug Reporting = PRESENT (Transferable Match)
NOT Missing

If CV says:
- “worked with MySQL queries in projects”

Then:
- SQL = PRESENT (Equivalent Match)
NOT Missing

------------------------------------------------------------
6. Missing rule (VERY STRICT)
------------------------------------------------------------
Only classify as Missing if ALL are true:
- No direct mention of the skill
- No equivalent tool evidence
- No transferable workflow evidence
- No project/work evidence suggesting the capability exists

If ANY doubt exists → DO NOT mark as Missing.

------------------------------------------------------------
7. Output rule for skills
------------------------------------------------------------
- skills_matched = ALL Direct + Equivalent + Transferable matches
- skills_missing = ONLY absolute Missing skills (high confidence absence only)

------------------------------------------------------------
8. Junior/intern weighting rule
------------------------------------------------------------
For junior/intern roles:
- Prioritize demonstrated capability over tool familiarity
- Assume learnability of tools when capability is proven
- Do NOT penalize missing enterprise tools (e.g., Jira) if workflow is demonstrated

============================================================
B. ROLE, SENIORITY/EXPERIENCE LEVEL, AND DOMAIN — strict reasoning (no flexibility)
============================================================
Unlike skills, do NOT apply semantic flexibility here:
- Role fit: the candidate's actual professional background/responsibilities must align with the job's
  role as described in the job description — not just a similar-sounding title.
- Experience level fit: compare the candidate's real years/seniority of *relevant* experience against
  the job's required level. Both directions are a mismatch:
  - Under-experienced relative to what the role demands -> not eligible.
  - Significantly OVER-experienced/over-qualified (e.g. a senior/staff-level candidate applying to a
    junior/entry-level role) -> not eligible — they are misaligned with the seniority the job is
    designed for.
  A candidate whose experience reasonably matches or is only slightly above/below the required level is
  fine.
- Domain fit: do NOT assume cross-domain experience is interchangeable. If the job requires a specific
  domain (e.g. CV, NLP, LLMs/agentic AI, embedded systems, fintech compliance, etc.), the CV must show
  explicit, genuine evidence of work in that domain — general software/engineering experience in an
  unrelated domain does not count, no matter how strong.

============================================================
Output
============================================================
Evaluate:
1. Role fit (per section B) — reasoning in `role_assessment`.
2. Experience level fit, including domain fit where the job specifies a domain (per section B) —
   reasoning in `experience_assessment`.
3. Skills fit (per section A) — populate `skills_matched` / `skills_missing`.
4. Project/experience relevance — do the candidate's described projects, work history, or
   accomplishments demonstrate hands-on experience relevant to what this job actually involves? —
   reasoning in `projects_assessment`.

Respond ONLY with a JSON object matching the required schema. Rules:
- `reason` must be a concise (under 200 characters) top-line summary of the overall verdict.
- Every other field must contain a specific, evidence-based explanation referencing what was actually
  found (or not found) in the candidate's CV/profile and the job description/requirements — never a
  generic or static statement.
- Mark eligible=true only when role, experience level, domain, and skills are a reasonable overall fit
  given the full job description. Mark eligible=false for clear mismatches in role, seniority, or
  domain (evaluated strictly), or for missing critical required skills after semantic skills reasoning.
- If information is sparse, reason from what is available. For skills, lean toward eligible only when
  nothing suggests a mismatch; for role/seniority/domain, sparse information that fails to demonstrate
  the required fit should be treated as a mismatch, not assumed away."""


async def check_ats_eligibility(
    candidate_id: str,
    job_posting_id: str,
    parsed_text: str | None = None,
) -> ATSCheckResult:
    conn = get_connection()
    try:
        cur = conn.cursor()

        if parsed_text is None:
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
                logger.warning("ATS: candidate profile not found for candidate_id=%s", candidate_id)
                raise ValueError(f"Candidate profile not found for candidate_id={candidate_id}")

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
            logger.warning("ATS: job posting not found for job_posting_id=%s", job_posting_id)
            raise ValueError(f"Job posting not found for job_posting_id={job_posting_id}")

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

    required_skills_str = (
        ", ".join(
            f"{name} ({level or 'any level'}){' [required]' if mandatory else ''}"
            for name, level, mandatory in required_skills_rows
        )
        if required_skills_rows
        else "Not specified"
    )

    if parsed_text:
        candidate_section = f"Candidate CV (full text — read for experience, projects, and skills):\n{parsed_text[:6000]}"
    else:
        candidate_skills_str = ", ".join(candidate_skills) if candidate_skills else "Not specified"
        candidate_section = f"""Candidate Profile (no CV uploaded — use this instead):
- Background: {candidate_bio or 'Not provided'}
- Experience Level: {experience_level or 'Not specified'}
- Current Role: {candidate_role or 'Not specified'}
- Skills: {candidate_skills_str}"""

    user_message = f"""{candidate_section}

Job Posting:
- Title: {designation}
- Required Experience Level: {experience_level_name}
- Role: {job_role}
- Full Description: {(job_description or 'Not specified')[:3000]}
- Required Skills: {required_skills_str}

Assess this candidate against this job posting per the instructions."""

    structured_llm = get_llm().with_structured_output(ATSCheckResult)
    try:
        result = await structured_llm.ainvoke(
            [
                ("system", _SYSTEM_PROMPT),
                ("user", user_message),
            ]
        )
        return result
    except Exception as exc:
        logger.error("ATS: LLM eligibility check failed for candidate=%s job=%s: %s", candidate_id, job_posting_id, exc)
        raise
