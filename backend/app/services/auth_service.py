import hashlib
import hmac
import secrets
import uuid
from pathlib import Path

from app.database import get_connection
from app.schemas.auth import CandidateProfileResponse, ExperienceLevelItem, JobRoleItem, RecruiterProfileResponse, RecruiterSigninResponse, RecruiterSignupResponse, SigninResponse, SignupMetadataResponse, SignupResponse, SkillItem
from app.services.cv_parser_service import parse_and_store_cv, store_resume_record


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:sha256:{salt}:{dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split(":")
    # stored format: pbkdf2:sha256:{salt}:{dk_hex}
    salt, dk_hex = parts[2], parts[3]
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def get_signup_metadata() -> SignupMetadataResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id, title, category FROM JobRoles WHERE is_active = 1 ORDER BY title")
        job_roles = [JobRoleItem(id=row[0], title=row[1], category=row[2]) for row in cur.fetchall()]

        cur.execute("SELECT id, name FROM ExperienceLevels ORDER BY min_years")
        experience_levels = [ExperienceLevelItem(id=row[0], name=row[1]) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT s.id, s.name, s.category, rs.job_role_id
            FROM SkillSets s
            LEFT JOIN RoleSkills rs ON rs.skill_id = s.id
            WHERE s.is_active = 1
            ORDER BY s.name
            """
        )
        skill_map: dict[int, SkillItem] = {}
        for row in cur.fetchall():
            skill_id, name, category, job_role_id = row[0], row[1], row[2], row[3]
            if skill_id not in skill_map:
                skill_map[skill_id] = SkillItem(id=skill_id, name=name, category=category, job_role_ids=[])
            if job_role_id is not None:
                skill_map[skill_id].job_role_ids.append(int(job_role_id))

        return SignupMetadataResponse(
            job_roles=job_roles,
            skills=list(skill_map.values()),
            experience_levels=experience_levels,
        )
    finally:
        conn.close()


def _get_experience_level_id(conn, experience_years: float) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id, min_years, max_years FROM ExperienceLevels ORDER BY min_years")
    rows = cur.fetchall()
    for row in rows:
        level_id, min_y, max_y = int(row[0]), int(row[1]), row[2]
        if max_y is None:
            if experience_years >= min_y:
                return level_id
        elif min_y <= experience_years < int(max_y):
            return level_id
    return int(rows[0][0]) if rows else 1


def signup_candidate(
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    job_role_id: int,
    skill_ids: list[int],
    experience_years: float,
    cv_content: bytes | None,
    cv_filename: str | None,
) -> SignupResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM Users WHERE email = ?", email)
        if cur.fetchone():
            raise ValueError("An account with this email already exists.")

        cur.execute("SELECT id FROM Roles WHERE name = 'Candidate'")
        row = cur.fetchone()
        candidate_role_id = int(row[0]) if row else 3

        experience_level_id = _get_experience_level_id(conn, experience_years)

        # Pre-generate IDs so parse_and_store_cv can reference the candidate
        user_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())

    finally:
        conn.close()

    # Parse and store CV outside the connection (opens its own connections internally)
    cv_data: dict = {"bio": None, "linkedin_url": None, "current_location": None, "total_experience_years": None, "skills": []}
    resume_url: str | None = None

    if cv_content:
        result = parse_and_store_cv(cv_content, cv_filename, candidate_id, store_resume=False)
        cv_data = result
        resume_url = result["file_url"]

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Re-check email uniqueness in case of race condition
        cur.execute("SELECT id FROM Users WHERE email = ?", email)
        if cur.fetchone():
            raise ValueError("An account with this email already exists.")

        cur.execute("SELECT id FROM Roles WHERE name = 'Candidate'")
        row = cur.fetchone()
        candidate_role_id = int(row[0]) if row else 3

        experience_level_id = _get_experience_level_id(conn, experience_years)

        if cv_data.get("total_experience_years") is not None:
            experience_level_id = _get_experience_level_id(conn, float(cv_data["total_experience_years"]))

        cur.execute(
            """
            INSERT INTO Users
                (id, email, password_hash, first_name, last_name, phone, role_id, is_active, is_verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 1, 0, GETDATE(), GETDATE())
            """,
            user_id,
            email,
            _hash_password(password),
            first_name,
            last_name,
            candidate_role_id,
        )

        cur.execute(
            """
            INSERT INTO CandidateProfiles
                (id, user_id, bio, resume_url, linkedin_url, experience_level_id, job_role_id, current_location, open_to_work, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, GETDATE())
            """,
            candidate_id,
            user_id,
            cv_data["bio"],
            resume_url,
            cv_data["linkedin_url"],
            experience_level_id,
            job_role_id,
            cv_data["current_location"],
        )

        # Merge manually selected skills with CV-extracted skills.
        # CV-parsed proficiency/years take precedence for overlapping skills.
        skill_data: dict[int, tuple[str, int]] = {}
        for sid in skill_ids:
            skill_data[sid] = ("Intermediate", int(experience_years))
        for cv_skill in cv_data.get("skills", []):
            sid = cv_skill["skill_id"]
            skill_data[sid] = (cv_skill["proficiency_level"], cv_skill["years_of_experience"])

        for skill_id, (proficiency, years) in skill_data.items():
            cur.execute(
                """
                INSERT INTO CandidateSkills (id, candidate_id, skill_id, proficiency_level, years_of_experience)
                VALUES (?, ?, ?, ?, ?)
                """,
                str(uuid.uuid4()),
                candidate_id,
                skill_id,
                proficiency,
                years,
            )

        conn.commit()
    finally:
        conn.close()

    # Insert Resumes row only after CandidateProfiles is committed (FK constraint)
    if cv_content and cv_data.get("resume_id"):
        store_resume_record(
            cv_data["resume_id"],
            candidate_id,
            cv_data["file_url"],
            cv_filename,
            cv_data.get("parsed_text"),
        )

    return SignupResponse(
        user_id=user_id,
        candidate_id=candidate_id,
        message="Account created successfully.",
    )


def signin_candidate(email: str, password: str) -> SigninResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM Users WHERE email = ? AND is_active = 1", email)
        row = cur.fetchone()
        if not row or not _verify_password(password, str(row[1])):
            raise ValueError("Invalid email or password.")
        user_id = str(row[0])
        cur.execute("SELECT id FROM CandidateProfiles WHERE user_id = ?", user_id)
        cp_row = cur.fetchone()
        if not cp_row:
            raise ValueError("No candidate profile found for this account.")
        return SigninResponse(
            user_id=user_id,
            candidate_id=str(cp_row[0]),
            message="Signed in successfully.",
        )
    finally:
        conn.close()


def signup_recruiter(
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    company_name: str,
    designation: str,
) -> RecruiterSignupResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM Users WHERE email = ?", email)
        if cur.fetchone():
            raise ValueError("An account with this email already exists.")

        cur.execute("SELECT id FROM Roles WHERE name = 'Recruiter'")
        row = cur.fetchone()
        recruiter_role_id = int(row[0]) if row else 2

        user_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO Users
                (id, email, password_hash, first_name, last_name, phone, role_id, is_active, is_verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 1, 0, GETDATE(), GETDATE())
            """,
            user_id,
            email,
            _hash_password(password),
            first_name,
            last_name,
            recruiter_role_id,
        )

        company_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO Companies
                (id, name, domain, website, industry, registration_number, verification_status, created_at)
            VALUES (?, ?, NULL, NULL, NULL, NULL, 'pending', GETDATE())
            """,
            company_id,
            company_name,
        )

        recruiter_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO RecruiterProfiles
                (id, user_id, company_id, designation, company_verified, joined_at)
            VALUES (?, ?, ?, ?, 0, GETDATE())
            """,
            recruiter_id,
            user_id,
            company_id,
            designation,
        )

        conn.commit()
        return RecruiterSignupResponse(
            user_id=user_id,
            recruiter_id=recruiter_id,
            message="Account created successfully.",
        )
    finally:
        conn.close()


def get_candidate_profile(candidate_id: str) -> CandidateProfileResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                u.first_name, u.last_name, u.email,
                jr.title,
                el.name, el.min_years, el.max_years,
                cp.bio, cp.linkedin_url, cp.current_location, cp.open_to_work, cp.resume_url,
                u.created_at
            FROM CandidateProfiles cp
            JOIN Users u ON u.id = cp.user_id
            LEFT JOIN JobRoles jr ON jr.id = cp.job_role_id
            LEFT JOIN ExperienceLevels el ON el.id = cp.experience_level_id
            WHERE cp.id = ?
            """,
            candidate_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Candidate not found")

        el_name = str(row[4]) if row[4] else ""
        el_min = int(row[5]) if row[5] is not None else 0
        el_max = row[6]
        if el_name:
            experience_level = f"{el_name} ({el_min}–{int(el_max)} yrs)" if el_max else f"{el_name} ({el_min}+ yrs)"
        else:
            experience_level = "Not specified"

        created_at = row[12]
        member_since = created_at.strftime("%B %Y") if created_at else ""

        cur.execute(
            """
            SELECT ss.name
            FROM CandidateSkills cs
            JOIN SkillSets ss ON ss.id = cs.skill_id
            WHERE cs.candidate_id = ?
            ORDER BY ss.name
            """,
            candidate_id,
        )
        skills = [str(r[0]) for r in cur.fetchall()]

        return CandidateProfileResponse(
            candidate_id=candidate_id,
            first_name=str(row[0]),
            last_name=str(row[1]),
            email=str(row[2]),
            job_role_title=str(row[3]) if row[3] else "Not specified",
            skills=skills,
            experience_level=experience_level,
            bio=str(row[7]) if row[7] else None,
            linkedin_url=str(row[8]) if row[8] else None,
            current_location=str(row[9]) if row[9] else None,
            open_to_work=bool(row[10]),
            resume_url=str(row[11]) if row[11] else None,
            member_since=member_since,
        )
    finally:
        conn.close()


def get_recruiter_profile(recruiter_id: str) -> RecruiterProfileResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                u.first_name, u.last_name, u.email,
                c.name, rp.designation, rp.company_verified,
                u.created_at
            FROM RecruiterProfiles rp
            JOIN Users u ON u.id = rp.user_id
            LEFT JOIN Companies c ON c.id = rp.company_id
            WHERE rp.id = ?
            """,
            recruiter_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Recruiter not found")

        created_at = row[6]
        member_since = created_at.strftime("%B %Y") if created_at else ""

        return RecruiterProfileResponse(
            recruiter_id=recruiter_id,
            first_name=str(row[0]),
            last_name=str(row[1]),
            email=str(row[2]),
            company_name=str(row[3]) if row[3] else "Not specified",
            designation=str(row[4]) if row[4] else "Not specified",
            company_verified=bool(row[5]),
            member_since=member_since,
        )
    finally:
        conn.close()


def update_candidate_cv(candidate_id: str, cv_content: bytes, cv_filename: str | None) -> str:
    """Parse a new CV, store it in Resumes, and update the candidate's profile + skills. Returns resume_id."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM CandidateProfiles WHERE id = ?", candidate_id)
        if not cur.fetchone():
            raise ValueError("Candidate profile not found.")
    finally:
        conn.close()

    result = parse_and_store_cv(cv_content, cv_filename, candidate_id)

    conn = get_connection()
    try:
        cur = conn.cursor()

        set_clauses: list[str] = ["resume_url = ?", "updated_at = GETDATE()"]
        params: list = [result["file_url"]]

        if result.get("bio"):
            set_clauses.insert(0, "bio = ?")
            params.insert(0, result["bio"])
        if result.get("linkedin_url"):
            set_clauses.insert(0, "linkedin_url = ?")
            params.insert(0, result["linkedin_url"])
        if result.get("current_location"):
            set_clauses.insert(0, "current_location = ?")
            params.insert(0, result["current_location"])
        if result.get("total_experience_years") is not None:
            exp_level_id = _get_experience_level_id(conn, float(result["total_experience_years"]))
            set_clauses.insert(0, "experience_level_id = ?")
            params.insert(0, exp_level_id)

        params.append(candidate_id)
        cur.execute(
            f"UPDATE CandidateProfiles SET {', '.join(set_clauses)} WHERE id = ?",
            *params,
        )

        for skill in result.get("skills", []):
            cur.execute(
                "SELECT id FROM CandidateSkills WHERE candidate_id = ? AND skill_id = ?",
                candidate_id,
                skill["skill_id"],
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """UPDATE CandidateSkills
                    SET proficiency_level = ?, years_of_experience = ?
                    WHERE id = ?""",
                    skill["proficiency_level"],
                    skill["years_of_experience"],
                    str(existing[0]),
                )
            else:
                cur.execute(
                    """INSERT INTO CandidateSkills (id, candidate_id, skill_id, proficiency_level, years_of_experience)
                    VALUES (?, ?, ?, ?, ?)""",
                    str(uuid.uuid4()),
                    candidate_id,
                    skill["skill_id"],
                    skill["proficiency_level"],
                    skill["years_of_experience"],
                )

        conn.commit()
    finally:
        conn.close()

    return result["resume_id"]


def signin_recruiter(email: str, password: str) -> RecruiterSigninResponse:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM Users WHERE email = ? AND is_active = 1", email)
        row = cur.fetchone()
        if not row or not _verify_password(password, str(row[1])):
            raise ValueError("Invalid email or password.")
        user_id = str(row[0])
        cur.execute("SELECT id FROM RecruiterProfiles WHERE user_id = ?", user_id)
        rp_row = cur.fetchone()
        if not rp_row:
            raise ValueError("No recruiter profile found for this account.")
        return RecruiterSigninResponse(
            user_id=user_id,
            recruiter_id=str(rp_row[0]),
            message="Signed in successfully.",
        )
    finally:
        conn.close()
