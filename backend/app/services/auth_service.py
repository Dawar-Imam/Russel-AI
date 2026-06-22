import hashlib
import hmac
import secrets
import uuid
from pathlib import Path

from app.database import get_connection
from app.schemas.auth import JobRoleItem, RecruiterSigninResponse, RecruiterSignupResponse, SigninResponse, SignupMetadataResponse, SignupResponse, SkillItem
from app.services.cv_parser_service import parse_pdf_cv

_UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads" / "resumes"


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

        return SignupMetadataResponse(job_roles=job_roles, skills=list(skill_map.values()))
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

        cv_data: dict[str, str | None] = {"bio": None, "linkedin_url": None, "current_location": None}
        resume_url: str | None = None

        if cv_content:
            cv_data = parse_pdf_cv(cv_content)
            _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            ext = Path(cv_filename).suffix if cv_filename else ".pdf"
            filename = f"{uuid.uuid4()}{ext}"
            (_UPLOADS_DIR / filename).write_bytes(cv_content)
            resume_url = f"uploads/resumes/{filename}"

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
            candidate_role_id,
        )

        candidate_id = str(uuid.uuid4())
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

        for skill_id in skill_ids:
            cur.execute(
                """
                INSERT INTO CandidateSkills (id, candidate_id, skill_id, proficiency_level, years_of_experience)
                VALUES (?, ?, ?, 'Intermediate', ?)
                """,
                str(uuid.uuid4()),
                candidate_id,
                skill_id,
                int(experience_years),
            )

        conn.commit()
        return SignupResponse(
            user_id=user_id,
            candidate_id=candidate_id,
            message="Account created successfully.",
        )
    finally:
        conn.close()


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
