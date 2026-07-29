import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.core.mailer import send_email
from app.database import db_cursor, escape_like
from app.schemas.auth import TAXONOMY_NAME_RE, CandidateProfileResponse, ExperienceLevelItem, JobRoleItem, RecruiterProfileResponse, RecruiterSigninResponse, RecruiterSignupResponse, SigninResponse, SignupMetadataResponse, SignupResponse, SkillItem
from app.services.cv_parser_service import parse_and_store_cv, store_resume_record

_OTP_TTL_MINUTES = 10


class NotVerifiedError(ValueError):
    """Raised on signin when the account's email OTP verification hasn't been
    completed yet — kept distinct from a plain bad-credentials ValueError so the
    endpoint can return 403 (account exists, just not usable yet) instead of 401."""


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


# OTP codes are hashed with the exact same PBKDF2 scheme as passwords — they're both
# just short secrets whose hash needs to be checked, not stored in the clear.
_hash_otp = _hash_password
_verify_otp = _verify_password


def _generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _create_and_send_otp(user_id: str, email: str, first_name: str) -> None:
    """(Re)issues a signup OTP: drops any previous still-pending code for this user
    (so only the latest one is ever valid — used by both signup and resend) and
    emails the new one."""
    otp = _generate_otp()
    with db_cursor() as (conn, cur):
        cur.execute("DELETE FROM OtpVerifications WHERE user_id = ?", user_id)
        cur.execute(
            "INSERT INTO OtpVerifications (id, user_id, otp_hash, expires_at) VALUES (?, ?, ?, ?)",
            str(uuid.uuid4()),
            user_id,
            _hash_otp(otp),
            datetime.utcnow() + timedelta(minutes=_OTP_TTL_MINUTES),
        )
        conn.commit()

    send_email(
        to=email,
        subject="Verify your Russel.AI account",
        body=(
            f"Hi {first_name},\n\n"
            f"Your verification code is: {otp}\n\n"
            f"This code expires in {_OTP_TTL_MINUTES} minutes."
        ),
    )


def verify_otp(user_id: str, otp_code: str) -> None:
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT id, otp_hash, expires_at FROM OtpVerifications WHERE user_id = ?",
            user_id,
        )
        row = cur.fetchone()
        if not row or not _verify_otp(otp_code, str(row[1])):
            raise ValueError("Invalid verification code.")
        if datetime.utcnow() > row[2]:
            raise ValueError("Verification code has expired — request a new one.")

        cur.execute("UPDATE Users SET is_verified = 1 WHERE id = ?", user_id)
        cur.execute("DELETE FROM OtpVerifications WHERE id = ?", str(row[0]))
        conn.commit()


def resend_otp(user_id: str) -> None:
    with db_cursor() as (conn, cur):
        cur.execute("SELECT email, first_name, is_verified FROM Users WHERE id = ?", user_id)
        row = cur.fetchone()
        if not row:
            raise ValueError("Account not found.")
        if row[2]:
            raise ValueError("This account is already verified.")
        email, first_name = str(row[0]), str(row[1])

    _create_and_send_otp(user_id, email, first_name)


def get_signup_metadata() -> SignupMetadataResponse:
    with db_cursor() as (conn, cur):
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


def search_job_roles(query: str, limit: int = 20) -> list[JobRoleItem]:
    with db_cursor() as (conn, cur):
        like = f"%{escape_like(query.strip())}%"
        cur.execute(
            "SELECT TOP (?) id, title, category FROM JobRoles WHERE is_active = 1 AND title LIKE ? ORDER BY title",
            limit,
            like,
        )
        return [JobRoleItem(id=row[0], title=row[1], category=row[2]) for row in cur.fetchall()]


def search_skills_for_role(role_id: int, query: str, limit: int = 20) -> list[SkillItem]:
    with db_cursor() as (conn, cur):
        like = f"%{escape_like(query.strip())}%"
        cur.execute(
            """
            SELECT TOP (?) s.id, s.name, s.category
            FROM SkillSets s
            JOIN RoleSkills rs ON rs.skill_id = s.id
            WHERE rs.job_role_id = ? AND s.is_active = 1 AND s.name LIKE ?
            ORDER BY s.name
            """,
            limit,
            role_id,
            like,
        )
        return [SkillItem(id=row[0], name=row[1], category=row[2], job_role_ids=[role_id]) for row in cur.fetchall()]


def get_or_create_skill(name: str, job_role_id: int | None = None) -> SkillItem:
    name = name.strip()
    if not TAXONOMY_NAME_RE.match(name):
        raise ValueError('Skill name must be 2-100 characters and contain at least one letter')
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT id, name, category FROM SkillSets WHERE LOWER(name) = LOWER(?) AND is_active = 1",
            name,
        )
        row = cur.fetchone()
        if row:
            skill_id, existing_name, category = int(row[0]), str(row[1]), row[2]
        else:
            # SkillSets.id has no IDENTITY property in the database, so the
            # next id must be computed and supplied explicitly. UPDLOCK+HOLDLOCK
            # serializes concurrent inserts against the same table to avoid a
            # duplicate-id race.
            cur.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM SkillSets WITH (UPDLOCK, HOLDLOCK)")
            skill_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO SkillSets (id, name, category, is_active) VALUES (?, ?, 'Custom', 1)",
                skill_id,
                name,
            )
            existing_name, category = name, "Custom"
            conn.commit()

        cur.execute("SELECT job_role_id FROM RoleSkills WHERE skill_id = ?", skill_id)
        job_role_ids = [int(r[0]) for r in cur.fetchall()]
        if job_role_id is not None and job_role_id not in job_role_ids:
            # Unlike SkillSets/JobRoles, RoleSkills.id IS an IDENTITY column.
            cur.execute(
                "INSERT INTO RoleSkills (job_role_id, skill_id) VALUES (?, ?)",
                job_role_id,
                skill_id,
            )
            conn.commit()
            job_role_ids.append(job_role_id)

        return SkillItem(id=skill_id, name=existing_name, category=category, job_role_ids=job_role_ids)


def get_or_create_job_role(title: str) -> JobRoleItem:
    title = title.strip()
    if not TAXONOMY_NAME_RE.match(title):
        raise ValueError('Job category title must be 2-100 characters and contain at least one letter')
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT id, title, category FROM JobRoles WHERE LOWER(title) = LOWER(?) AND is_active = 1",
            title,
        )
        row = cur.fetchone()
        if row:
            role_id, existing_title, category = int(row[0]), str(row[1]), row[2]
        else:
            # JobRoles.id has no IDENTITY property in the database, so the
            # next id must be computed and supplied explicitly. UPDLOCK+HOLDLOCK
            # serializes concurrent inserts against the same table to avoid a
            # duplicate-id race.
            cur.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM JobRoles WITH (UPDLOCK, HOLDLOCK)")
            role_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO JobRoles (id, title, category, is_active) VALUES (?, ?, 'Custom', 1)",
                role_id,
                title,
            )
            existing_title, category = title, "Custom"
            conn.commit()

        return JobRoleItem(id=role_id, title=existing_title, category=category)


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
    with db_cursor() as (conn, cur):
        cur.execute("SELECT id FROM Roles WHERE name = 'Candidate'")
        row = cur.fetchone()
        candidate_role_id = int(row[0]) if row else 3

        # Email is unique per role, not globally — the same email may already have a
        # Recruiter account, which is fine; only a second Candidate account is blocked.
        cur.execute("SELECT id FROM Users WHERE email = ? AND role_id = ?", email, candidate_role_id)
        if cur.fetchone():
            raise ValueError("A candidate account with this email already exists.")

        experience_level_id = _get_experience_level_id(conn, experience_years)

        # Pre-generate IDs so parse_and_store_cv can reference the candidate
        user_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())

    # Parse and store CV outside the connection (opens its own connections internally)
    cv_data: dict = {"bio": None, "linkedin_url": None, "current_location": None, "total_experience_years": None, "skills": []}
    resume_url: str | None = None

    if cv_content:
        result = parse_and_store_cv(cv_content, cv_filename, candidate_id, store_resume=False)
        cv_data = result
        resume_url = result["file_url"]

    with db_cursor() as (conn, cur):
        # Re-check uniqueness (scoped to this role) in case of race condition
        cur.execute("SELECT id FROM Users WHERE email = ? AND role_id = ?", email, candidate_role_id)
        if cur.fetchone():
            raise ValueError("A candidate account with this email already exists.")

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

    # Insert Resumes row only after CandidateProfiles is committed (FK constraint)
    if cv_content and cv_data.get("resume_id"):
        store_resume_record(
            cv_data["resume_id"],
            candidate_id,
            cv_data["file_url"],
            cv_filename,
            cv_data.get("parsed_text"),
        )

    _create_and_send_otp(user_id, email, first_name)

    return SignupResponse(
        user_id=user_id,
        candidate_id=candidate_id,
        message="Account created successfully. Check your email for a verification code.",
    )


def signin_candidate(email: str, password: str) -> SigninResponse:
    with db_cursor() as (conn, cur):
        # Joined to CandidateProfiles (not a plain Users lookup) so the correct row is
        # picked even when the same email also has a separate Recruiter account.
        cur.execute(
            """
            SELECT u.id, u.password_hash, u.is_verified, cp.id
            FROM Users u
            JOIN CandidateProfiles cp ON cp.user_id = u.id
            WHERE u.email = ? AND u.is_active = 1
            """,
            email,
        )
        row = cur.fetchone()
        if not row or not _verify_password(password, str(row[1])):
            raise ValueError("Invalid email or password.")
        if not row[2]:
            raise NotVerifiedError("Please verify your email before signing in.")
        return SigninResponse(
            user_id=str(row[0]),
            candidate_id=str(row[3]),
            message="Signed in successfully.",
        )


def signup_recruiter(
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    company_name: str,
    designation: str,
) -> RecruiterSignupResponse:
    with db_cursor() as (conn, cur):
        cur.execute("SELECT id FROM Roles WHERE name = 'Recruiter'")
        row = cur.fetchone()
        recruiter_role_id = int(row[0]) if row else 2

        # Email is unique per role, not globally — the same email may already have a
        # Candidate account, which is fine; only a second Recruiter account is blocked.
        cur.execute("SELECT id FROM Users WHERE email = ? AND role_id = ?", email, recruiter_role_id)
        if cur.fetchone():
            raise ValueError("A recruiter account with this email already exists.")

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

    _create_and_send_otp(user_id, email, first_name)

    return RecruiterSignupResponse(
        user_id=user_id,
        recruiter_id=recruiter_id,
        message="Account created successfully. Check your email for a verification code.",
    )


def get_candidate_profile(candidate_id: str) -> CandidateProfileResponse:
    with db_cursor() as (conn, cur):
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


def get_recruiter_profile(recruiter_id: str) -> RecruiterProfileResponse:
    with db_cursor() as (conn, cur):
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


def update_candidate_cv(candidate_id: str, cv_content: bytes, cv_filename: str | None) -> str:
    """Parse a new CV, store it in Resumes, and update the candidate's profile + skills. Returns resume_id."""
    with db_cursor() as (conn, cur):
        cur.execute("SELECT id FROM CandidateProfiles WHERE id = ?", candidate_id)
        if not cur.fetchone():
            raise ValueError("Candidate profile not found.")

    result = parse_and_store_cv(cv_content, cv_filename, candidate_id)

    with db_cursor() as (conn, cur):
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

    return result["resume_id"]


def signin_recruiter(email: str, password: str) -> RecruiterSigninResponse:
    with db_cursor() as (conn, cur):
        # Joined to RecruiterProfiles (not a plain Users lookup) so the correct row is
        # picked even when the same email also has a separate Candidate account.
        cur.execute(
            """
            SELECT u.id, u.password_hash, u.is_verified, rp.id
            FROM Users u
            JOIN RecruiterProfiles rp ON rp.user_id = u.id
            WHERE u.email = ? AND u.is_active = 1
            """,
            email,
        )
        row = cur.fetchone()
        if not row or not _verify_password(password, str(row[1])):
            raise ValueError("Invalid email or password.")
        if not row[2]:
            raise NotVerifiedError("Please verify your email before signing in.")
        return RecruiterSigninResponse(
            user_id=str(row[0]),
            recruiter_id=str(row[3]),
            message="Signed in successfully.",
        )
