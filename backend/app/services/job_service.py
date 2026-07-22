import json
import uuid
from datetime import datetime, timezone

from app.ai.ai_services.ats_service import parse_ats_criteria
from app.database import db_cursor, escape_like
from app.schemas.jobs import (
    ATSCriteriaSummary,
    ATSCriterionSummary,
    CandidateInfo,
    CandidatePanelResponse,
    CandidateSkillItem,
    EvaluationQuestionItem,
    InterviewProgressItem,
    InterviewRoundTypeItem,
    JobInterviewRoundItem,
    JobListItem,
    JobPostRequest,
    JobPostResponse,
    JobStatsResponse,
    JobStatsRound,
    JobUpdateRequest,
    RerunAtsResponse,
    RerunAtsStatusResponse,
    RoundCandidateItem,
)
from app.services.ats_lock import ats_rerun_batch_key, get_redis_client, set_latest_rerun_generation_batch

_ATS_RERUN_BATCH_TTL_SECONDS = 3600


def get_job_rounds(job_id: str) -> list[JobInterviewRoundItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT ir.round_order, irt.name, ir.failing_criteria, ir.description, ir.time_limit_minutes
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            WHERE ir.job_posting_id = ? AND ir.is_active = 1
            ORDER BY ir.round_order
            """,
            job_id,
        )
        return [
            JobInterviewRoundItem(
                round_order=int(row[0]),
                round_type_name=str(row[1]),
                failing_criteria=int(row[2]) if row[2] is not None else None,
                description=str(row[3]) if row[3] else None,
                time_limit_minutes=int(row[4]) if row[4] is not None else None,
            )
            for row in cur.fetchall()
        ]


def list_interview_round_types() -> list[InterviewRoundTypeItem]:
    with db_cursor() as (conn, cur):
        cur.execute("SELECT id, name, description FROM InterviewRoundTypes ORDER BY id")
        return [
            InterviewRoundTypeItem(id=int(row[0]), name=str(row[1]), description=str(row[2]) if row[2] else None)
            for row in cur.fetchall()
        ]


def post_job(data: JobPostRequest) -> JobPostResponse:
    with db_cursor() as (conn, cur):
        cur.execute("SELECT company_id FROM RecruiterProfiles WHERE id = ?", data.recruiter_id)
        row = cur.fetchone()
        if not row:
            raise ValueError("Recruiter profile not found.")
        company_id = str(row[0])

        job_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO JobPostings
                (id, recruiter_id, company_id, job_role_id, experience_level_id, description,
                 location, job_type, salary_range, status, posted_at, expires_at, ats_criteria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', GETDATE(), ?, ?)
            """,
            job_id,
            data.recruiter_id,
            company_id,
            data.job_role_id,
            data.experience_level_id,
            data.description,
            data.location,
            data.job_type,
            data.salary_range,
            data.expires_at,
            json.dumps({
                "criteria": [c.model_dump() for c in data.ats_criteria],
                "qualify_threshold": data.qualify_threshold,
                "overqualify_threshold": data.overqualify_threshold,
                "auto_reject_overqualified": data.auto_reject_overqualified,
            }),
        )

        for skill_id in data.skill_ids:
            cur.execute(
                """
                INSERT INTO JobRequiredSkills (id, job_id, skill_id, proficiency_level, is_mandatory)
                VALUES (?, ?, ?, 'Intermediate', 1)
                """,
                str(uuid.uuid4()),
                job_id,
                skill_id,
            )

        for round_input in data.interview_rounds:
            round_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO InterviewRounds
                    (id, job_posting_id, interview_round_type_id, round_order,
                     description, failing_criteria, time_limit_minutes, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                round_id,
                job_id,
                round_input.round_type_id,
                round_input.round_order,
                round_input.description,
                round_input.failing_criteria,
                round_input.time_limit_minutes,
            )

        conn.commit()
        return JobPostResponse(job_id=job_id, message="Job posted successfully.")


def _row_to_job(row) -> JobListItem:
    skills_raw = row[9]
    required_skills = [s.strip() for s in skills_raw.split(',') if s.strip()] if skills_raw else []
    return JobListItem(
        id=str(row[0]),
        description=str(row[1]),
        company=str(row[2]),
        job_role_title=str(row[3]),
        location=str(row[4]),
        job_type=str(row[5]),
        salary_range=str(row[6]) if row[6] else None,
        posted_at=str(row[7]),
        expires_at=str(row[8]) if row[8] else None,
        required_skills=required_skills,
        job_role_id=int(row[10]),
        experience_level_name=str(row[11]),
        experience_level_id=int(row[12]),
        status=str(row[13]) if row[13] else 'active',
    )


_JOB_SELECT = """
    SELECT jp.id, jp.description, c.name, jr.title,
           jp.location, jp.job_type, jp.salary_range,
           CONVERT(varchar, jp.posted_at, 127),
           CONVERT(varchar, jp.expires_at, 127),
           STRING_AGG(s.name, ',') WITHIN GROUP (ORDER BY s.name),
           jp.job_role_id, el.name, jp.experience_level_id,
           jp.status
    FROM JobPostings jp
    JOIN Companies c ON c.id = jp.company_id
    JOIN JobRoles jr ON jr.id = jp.job_role_id
    JOIN ExperienceLevels el ON el.id = jp.experience_level_id
    LEFT JOIN JobRequiredSkills jrs ON jrs.job_id = jp.id
    LEFT JOIN SkillSets s ON s.id = jrs.skill_id
"""

_JOB_GROUP_BY = """
    GROUP BY jp.id, jp.description, c.name, jr.title,
             jp.location, jp.job_type, jp.salary_range, jp.posted_at, jp.expires_at,
             jp.job_role_id, el.name, jp.experience_level_id, jp.status
"""

# Recruiter-only variant — adds jp.ats_criteria so the dashboard can display a job's
# configured ATS weighting/thresholds. Not used for the public/candidate job list so
# scoring thresholds aren't exposed to candidates.
_RECRUITER_JOB_SELECT = """
    SELECT jp.id, jp.description, c.name, jr.title,
           jp.location, jp.job_type, jp.salary_range,
           CONVERT(varchar, jp.posted_at, 127),
           CONVERT(varchar, jp.expires_at, 127),
           STRING_AGG(s.name, ',') WITHIN GROUP (ORDER BY s.name),
           jp.job_role_id, el.name, jp.experience_level_id,
           jp.status, jp.ats_criteria
    FROM JobPostings jp
    JOIN Companies c ON c.id = jp.company_id
    JOIN JobRoles jr ON jr.id = jp.job_role_id
    JOIN ExperienceLevels el ON el.id = jp.experience_level_id
    LEFT JOIN JobRequiredSkills jrs ON jrs.job_id = jp.id
    LEFT JOIN SkillSets s ON s.id = jrs.skill_id
"""

_RECRUITER_JOB_GROUP_BY = """
    GROUP BY jp.id, jp.description, c.name, jr.title,
             jp.location, jp.job_type, jp.salary_range, jp.posted_at, jp.expires_at,
             jp.job_role_id, el.name, jp.experience_level_id, jp.status, jp.ats_criteria
"""


def _row_to_recruiter_job(row) -> JobListItem:
    job = _row_to_job(row)
    parsed = parse_ats_criteria(row[14])
    job.ats_criteria = ATSCriteriaSummary(
        has_config=parsed.has_config,
        criteria=[ATSCriterionSummary(section=c["section"], weight=c["weight"]) for c in parsed.criteria],
        qualify_threshold=parsed.qualify_threshold,
        overqualify_threshold=parsed.overqualify_threshold,
        auto_reject_overqualified=parsed.auto_reject_overqualified,
    )
    return job


def list_jobs(
    job_role_id: int | None = None,
    experience_level_id: int | None = None,
    location: str | None = None,
    job_type: str | None = None,
    salary_range: str | None = None,
    candidate_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[JobListItem]:
    with db_cursor() as (conn, cur):
        conditions = [
            "jp.status = 'active'",
            "(jp.expires_at IS NULL OR CAST(jp.expires_at AS DATE) >= CAST(GETDATE() AS DATE))",
        ]
        params: list = []

        location = (location or "").strip() or None
        salary_range = (salary_range or "").strip() or None
        candidate_id = (candidate_id or "").strip() or None

        if job_role_id is not None:
            conditions.append("jp.job_role_id = ?")
            params.append(job_role_id)
        if experience_level_id is not None:
            conditions.append("jp.experience_level_id = ?")
            params.append(experience_level_id)
        if location:
            conditions.append("jp.location LIKE ?")
            params.append(f"%{escape_like(location)}%")
        if job_type:
            conditions.append("jp.job_type = ?")
            params.append(job_type)
        if salary_range:
            conditions.append("jp.salary_range LIKE ?")
            params.append(f"%{escape_like(salary_range)}%")
        if candidate_id:
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM Applications a WHERE a.job_id = jp.id AND a.candidate_id = ?)"
            )
            params.append(candidate_id)

        where_clause = "WHERE " + " AND ".join(conditions) + " "
        params.extend([offset, limit])

        sql = (
            _JOB_SELECT
            + where_clause
            + _JOB_GROUP_BY
            + "ORDER BY jp.posted_at DESC "
            + "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )

        cur.execute(sql, *params)
        return [_row_to_job(row) for row in cur.fetchall()]


def list_recruiter_jobs(recruiter_id: str) -> list[JobListItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            _RECRUITER_JOB_SELECT
            + "WHERE jp.recruiter_id = ?"
            + _RECRUITER_JOB_GROUP_BY
            + "ORDER BY jp.posted_at DESC",
            recruiter_id,
        )
        return [_row_to_recruiter_job(row) for row in cur.fetchall()]


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_job_stats(job_id: str) -> JobStatsResponse:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT jr.title, jp.description, jp.status
            FROM JobPostings jp
            JOIN JobRoles jr ON jr.id = jp.job_role_id
            WHERE jp.id = ?
            """,
            job_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Job not found")
        job_title, description, status = str(row[0]), str(row[1]), str(row[2])

        cur.execute(
            "SELECT s.name FROM JobRequiredSkills jrs JOIN SkillSets s ON s.id = jrs.skill_id WHERE jrs.job_id = ?",
            job_id,
        )
        required_skills = [str(r[0]) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ir.round_order, irt.name, ir.failing_criteria,
                   COUNT(DISTINCT i.application_id) AS cnt
            FROM InterviewRounds ir
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i ON i.interview_round_id = ir.id
            WHERE ir.job_posting_id = ? AND ir.is_active = 1
            GROUP BY ir.round_order, irt.name, ir.failing_criteria
            ORDER BY ir.round_order
            """,
            job_id,
        )
        rounds = [
            JobStatsRound(
                round_order=int(r[0]),
                round_type_name=str(r[1]),
                failing_criteria=int(r[2]) if r[2] is not None else None,
                applicants_count=int(r[3]),
            )
            for r in cur.fetchall()
        ]

        cur.execute("SELECT COUNT(*) FROM Applications WHERE job_id = ?", job_id)
        total_applicants = int(cur.fetchone()[0])

        cur.execute(
            """
            WITH RoundCount AS (
                SELECT COUNT(*) AS cnt
                FROM InterviewRounds
                WHERE job_posting_id = ? AND is_active = 1
            ),
            PassedPerApp AS (
                SELECT i.application_id, COUNT(DISTINCT i.interview_round_id) AS passed
                FROM Interviews i
                JOIN InterviewRounds ir ON ir.id = i.interview_round_id
                WHERE ir.job_posting_id = ? AND i.status = 'Pass'
                GROUP BY i.application_id
            )
            SELECT COUNT(*)
            FROM PassedPerApp p
            CROSS JOIN RoundCount r
            WHERE p.passed = r.cnt AND r.cnt > 0
            """,
            job_id,
            job_id,
        )
        passed_all_rounds = int(cur.fetchone()[0])

        cur.execute("SELECT COUNT(*) FROM Applications WHERE job_id = ? AND status = 'HIRED'", job_id)
        hired_count = int(cur.fetchone()[0])

        return JobStatsResponse(
            job_title=job_title,
            description=description,
            status=status,
            required_skills=required_skills,
            rounds=rounds,
            total_applicants=total_applicants,
            passed_all_rounds=passed_all_rounds,
            hired_count=hired_count,
        )


def get_round_candidates(job_id: str, round_order: int) -> list[RoundCandidateItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT cp.id, a.id, i.id,
                   u.first_name + ' ' + u.last_name,
                   i.status
            FROM InterviewRounds ir
            JOIN Interviews i ON i.interview_round_id = ir.id
            JOIN Applications a ON a.id = i.application_id
            JOIN CandidateProfiles cp ON cp.id = a.candidate_id
            JOIN Users u ON u.id = cp.user_id
            WHERE ir.job_posting_id = ? AND ir.round_order = ? AND ir.is_active = 1
            ORDER BY u.first_name, u.last_name
            """,
            job_id,
            round_order,
        )
        return [
            RoundCandidateItem(
                candidate_id=str(r[0]),
                application_id=str(r[1]),
                interview_id=str(r[2]),
                name=str(r[3]),
                status=str(r[4]),
            )
            for r in cur.fetchall()
        ]


def get_candidate_panel(application_id: str, interview_id: str) -> CandidatePanelResponse:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT u.first_name, u.last_name, u.email, cp.bio, cp.current_location,
                   el.name, jr.title, cp.id, u.phone, cp.linkedin_url,
                   el.min_years, el.max_years
            FROM Applications a
            JOIN CandidateProfiles cp ON cp.id = a.candidate_id
            JOIN Users u ON u.id = cp.user_id
            LEFT JOIN ExperienceLevels el ON el.id = cp.experience_level_id
            LEFT JOIN JobRoles jr ON jr.id = cp.job_role_id
            WHERE a.id = ?
            """,
            application_id,
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Application not found")
        first_name = str(row[0])
        last_name = str(row[1])
        email = str(row[2])
        bio = str(row[3]) if row[3] else None
        current_location = str(row[4]) if row[4] else None
        experience_level = str(row[5]) if row[5] else None
        job_role = str(row[6]) if row[6] else None
        candidate_id = str(row[7])
        phone = str(row[8]) if row[8] else None
        linkedin_url = str(row[9]) if row[9] else None
        experience_years_min = int(row[10]) if row[10] is not None else None
        experience_years_max = int(row[11]) if row[11] is not None else None

        cur.execute(
            """
            SELECT s.name, cs.proficiency_level
            FROM CandidateSkills cs
            JOIN SkillSets s ON s.id = cs.skill_id
            WHERE cs.candidate_id = ?
            ORDER BY s.name
            """,
            candidate_id,
        )
        skills = [
            CandidateSkillItem(name=str(r[0]), proficiency_level=str(r[1]) if r[1] else None)
            for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT ir.round_order, irt.name, i.status, i.result,
                   CONVERT(varchar, i.completed_at, 127), i.id
            FROM Applications a
            JOIN InterviewRounds ir ON ir.job_posting_id = a.job_id
            JOIN InterviewRoundTypes irt ON irt.id = ir.interview_round_type_id
            LEFT JOIN Interviews i ON i.interview_round_id = ir.id AND i.application_id = a.id
            WHERE a.id = ? AND ir.is_active = 1
            ORDER BY ir.round_order
            """,
            application_id,
        )
        progress = [
            InterviewProgressItem(
                round_order=int(r[0]),
                round_type_name=str(r[1]),
                status=str(r[2]) if r[2] else None,
                result=float(r[3]) if r[3] is not None else None,
                completed_at=str(r[4]) if r[4] else None,
                interview_id=str(r[5]) if r[5] else None,
            )
            for r in cur.fetchall()
        ]

        cur.execute("SELECT status FROM Interviews WHERE id = ?", interview_id)
        iv_row = cur.fetchone()
        iv_status = str(iv_row[0]) if iv_row else None

        evaluation = None
        if iv_status in ('Pass', 'Failed'):
            cur.execute(
                """
                SELECT q.question_text, iq.candidate_answer, iq.score, iq.notes
                FROM InterviewQuestions iq
                JOIN Questions q ON q.id = iq.question_id
                WHERE iq.interview_id = ?
                ORDER BY q.created_at
                """,
                interview_id,
            )
            evaluation = [
                EvaluationQuestionItem(
                    question_text=str(r[0]),
                    candidate_answer=str(r[1]) if r[1] else None,
                    score=int(r[2]) if r[2] is not None else None,
                    notes=str(r[3]) if r[3] else None,
                )
                for r in cur.fetchall()
            ]

        return CandidatePanelResponse(
            candidate=CandidateInfo(
                first_name=first_name,
                last_name=last_name,
                email=email,
                bio=bio,
                current_location=current_location,
                experience_level=experience_level,
                job_role=job_role,
                skills=skills,
                phone=phone,
                linkedin_url=linkedin_url,
                experience_years_min=experience_years_min,
                experience_years_max=experience_years_max,
            ),
            progress=progress,
            evaluation=evaluation,
        )


def get_job_required_skills(job_id: str):
    from app.schemas.jobs import JobSkillOptionItem

    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT s.id, s.name
            FROM JobRequiredSkills jrs
            JOIN SkillSets s ON s.id = jrs.skill_id
            WHERE jrs.job_id = ?
            ORDER BY s.name
            """,
            job_id,
        )
        return [JobSkillOptionItem(id=int(r[0]), name=str(r[1])) for r in cur.fetchall()]


def update_job(job_id: str, recruiter_id: str, data: JobUpdateRequest) -> JobPostResponse:
    """Recruiter edit of an already-posted job — everything except `interview_rounds`
    (see JobUpdateRequest) is editable: candidates may already have Interviews rows tied
    to the existing round set, so rounds stay locked once a job is live.
    """
    with db_cursor() as (conn, cur):
        cur.execute("SELECT recruiter_id, ats_criteria FROM JobPostings WHERE id = ?", job_id)
        row = cur.fetchone()
        if not row:
            raise ValueError("Job not found")
        if str(row[0]).lower() != recruiter_id.lower():
            raise ValueError("Only the recruiter who posted this job may edit it.")

        updates: list[str] = []
        params: list = []
        if data.description is not None:
            updates.append("description = ?")
            params.append(data.description)
        if data.location is not None:
            updates.append("location = ?")
            params.append(data.location)
        if data.job_type is not None:
            updates.append("job_type = ?")
            params.append(data.job_type)
        if data.salary_range is not None:
            updates.append("salary_range = ?")
            params.append(data.salary_range)
        if data.expires_at is not None:
            updates.append("expires_at = ?")
            params.append(data.expires_at)
        if data.status is not None:
            updates.append("status = ?")
            params.append(data.status)

        if (
            data.ats_criteria is not None
            or data.qualify_threshold is not None
            or data.overqualify_threshold is not None
            or data.auto_reject_overqualified is not None
            # Required skills are part of what ATS actually scores against too — a
            # skills-only edit must count as a criteria change for staleness purposes,
            # same as editing weights/thresholds directly.
            or data.skill_ids is not None
        ):
            current = parse_ats_criteria(row[1])
            updates.append("ats_criteria = ?")
            params.append(json.dumps({
                "criteria": [c.model_dump() for c in data.ats_criteria] if data.ats_criteria is not None else current.criteria,
                "qualify_threshold": data.qualify_threshold if data.qualify_threshold is not None else current.qualify_threshold,
                "overqualify_threshold": data.overqualify_threshold if data.overqualify_threshold is not None else current.overqualify_threshold,
                "auto_reject_overqualified": data.auto_reject_overqualified if data.auto_reject_overqualified is not None else current.auto_reject_overqualified,
            }))
            # Staleness versioning (see Applications.ats_run_version) — bump whenever the
            # criteria (or required skills, which ATS also scores against) actually change,
            # so select_applications_for_ats_rerun and the interview-completion hook can
            # tell which already-scored candidates need re-scoring against the new criteria.
            updates.append("ats_criteria_version = ats_criteria_version + 1")

        if updates:
            params.append(job_id)
            cur.execute(f"UPDATE JobPostings SET {', '.join(updates)} WHERE id = ?", *params)

        if data.skill_ids is not None:
            cur.execute("DELETE FROM JobRequiredSkills WHERE job_id = ?", job_id)
            for skill_id in data.skill_ids:
                cur.execute(
                    """
                    INSERT INTO JobRequiredSkills (id, job_id, skill_id, proficiency_level, is_mandatory)
                    VALUES (?, ?, ?, 'Intermediate', 1)
                    """,
                    str(uuid.uuid4()), job_id, skill_id,
                )

        conn.commit()
        return JobPostResponse(job_id=job_id, message="Job updated successfully.")


# ── Recruiter-triggered ATS rerun ────────────────────────────────────────────────


def select_applications_for_ats_rerun(job_id: str) -> tuple[list[str], int, int]:
    """Returns (selected_application_ids, skipped_pending_count, not_stale_count) for a
    job-scoped ATS rerun. not_stale_count is how many otherwise-eligible applications
    were skipped purely because they were already scored against the job's current
    ats_criteria_version — surfaced to the recruiter (job_service.rerun_ats_for_job) so
    a 0-queued rerun reads as "nothing to do, criteria haven't changed" instead of
    looking like the button silently did nothing.

    Exclusion criteria (re-checked per-application at execution time in
    application_service.rerun_ats_and_persist, since this snapshot can go stale before
    each Celery task actually runs) — deliberately narrow: a rerun is allowed to fully
    re-decide a HIRED/REJECTED application, one with an already-Failed round, or one that
    already cleared every round ("full overwrite, no special-casing" — see
    application_service._persist_ats_rerun_result, which resets these like a fresh
    applicant on a status-flipping verdict). Only:
      - application has a round currently In Progress — never even started for these;
        see job_service.rerun_ats_for_job, which separately counts and surfaces them
        to the recruiter so it's visible they'll be screened once their round ends
      - already-scored (non-ATS_PENDING) application whose ats_run_version is not
        older than the job's current ats_criteria_version — it was already scored
        against the current criteria, re-scoring it again would be a no-op

    ATS_PENDING applications are still included regardless of version — they've never
    been scored at all, so staleness doesn't apply; application_service.run_ats_for_application
    and rerun_ats_and_persist share the same per-application Redis lock (ats_lock.py), so if
    the original apply-time run is genuinely still in flight, the rerun task backs off
    cleanly instead of racing it; there's no true Celery-task revocation for the original
    (non-Celery, request-scoped) apply-time run.
    """
    from app.services.application_service import is_excluded_from_ats_rerun

    with db_cursor() as (conn, cur):
        cur.execute("SELECT ats_criteria_version FROM JobPostings WHERE id = ?", job_id)
        row = cur.fetchone()
        criteria_version = int(row[0]) if row else 0

        cur.execute("SELECT id, status, ats_run_version FROM Applications WHERE job_id = ?", job_id)
        rows = [(str(r[0]), str(r[1]), int(r[2])) for r in cur.fetchall()]

        selected: list[str] = []
        skipped_pending = 0
        not_stale_count = 0
        for application_id, status, ats_run_version in rows:
            if status != "ATS_PENDING" and ats_run_version >= criteria_version:
                not_stale_count += 1
                continue
            if is_excluded_from_ats_rerun(cur, application_id, job_id):
                continue
            selected.append(application_id)
            if status == "ATS_PENDING":
                skipped_pending += 1

    return selected, skipped_pending, not_stale_count


def rerun_ats_for_job(job_id: str, recruiter_id: str | None) -> RerunAtsResponse:
    """Recruiter-triggered ATS rerun entry point: selects candidate application_ids for
    this job and dispatches a single Celery task (app.tasks.ats_rerun_tasks.run_batch) for
    the whole batch — that task fans the applications back out itself via a
    ThreadPoolExecutor, so Celery only ever schedules one task per rerun request rather
    than one per application. Each application still gets check_ats_eligibility run fresh
    against the job's current requirements/thresholds and persisted via
    application_service.rerun_ats_and_persist, unchanged.

    Returns as soon as the batch is dispatched — it never waits for run_batch, its
    ThreadPoolExecutor fan-out, or any retry to finish. Callers poll
    get_ats_rerun_status(job_id) separately for A/B progress.

    Before dispatch, stamps every selected application_id with a fresh rerun generation
    token (ats_lock.set_latest_rerun_generation_batch) so that if a previous rerun batch
    for this job is still retrying one of these same applications, that stale attempt
    detects it's been superseded and stops instead of racing this one.
    """
    from app.tasks import ats_rerun_tasks

    with db_cursor() as (conn, cur):
        cur.execute("SELECT id FROM JobPostings WHERE id = ?", job_id)
        if not cur.fetchone():
            raise ValueError("Job not found")
        cur.execute("SELECT COUNT(*) FROM Applications WHERE job_id = ?", job_id)
        total_applications = int(cur.fetchone()[0])

        # Standalone, independent of the selection loop above — purely for surfacing to
        # the recruiter why some excluded candidates weren't queued: they're mid-interview
        # and is_excluded_from_ats_rerun already keeps them out of `selected` entirely.
        cur.execute(
            """
            SELECT COUNT(DISTINCT a.id) FROM Applications a
            JOIN Interviews i ON i.application_id = a.id
            WHERE a.job_id = ? AND i.status = 'In Progress'
            """,
            job_id,
        )
        in_progress_count = int(cur.fetchone()[0])

    selected, skipped_pending, not_stale_count = select_applications_for_ats_rerun(job_id)
    excluded = total_applications - len(selected)

    if selected:
        rerun_id = str(uuid.uuid4())
        set_latest_rerun_generation_batch(selected, rerun_id)
        ats_rerun_tasks.run_batch.delay(selected, recruiter_id, rerun_id)

    try:
        get_redis_client().set(
            ats_rerun_batch_key(job_id),
            json.dumps({
                "application_ids": selected,
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
            }),
            ex=_ATS_RERUN_BATCH_TTL_SECONDS,
        )
    except Exception:
        # Batch-progress polling degrades to "unknown" if Redis is unreachable — the
        # reruns themselves are already dispatched and will still run regardless.
        pass

    return RerunAtsResponse(
        queued=len(selected),
        skipped_pending=skipped_pending,
        excluded=excluded,
        in_progress_count=in_progress_count,
        not_stale_count=not_stale_count,
        total_applications=total_applications,
        message=(
            "No applicants for this job yet."
            if total_applications == 0
            else f"ATS rerun queued for {len(selected)} candidate(s)."
        ),
    )


def get_ats_rerun_status(job_id: str) -> RerunAtsStatusResponse:
    """Polled by the recruiter dashboard while a rerun batch is in flight.

    An application counts as "settled" (done, one way or another) either because its
    ats_evaluated_at was bumped past dispatch time (a real rerun persisted), or because
    it's become excluded since dispatch (application_service.is_excluded_from_ats_rerun —
    e.g. its interview went In Progress in the window between selection and this
    application's turn in the batch's ThreadPoolExecutor). Without the latter check, such
    an application's ats_evaluated_at never moves — rerun_ats_and_persist returns EXCLUDED
    and writes nothing — so `completed` would permanently stay below `total` and this
    endpoint would report in_progress=True forever even though the Celery batch itself
    has long since finished.
    """
    from app.services.application_service import is_excluded_from_ats_rerun

    try:
        raw = get_redis_client().get(ats_rerun_batch_key(job_id))
    except Exception:
        raw = None

    if not raw:
        return RerunAtsStatusResponse(total_queued=0, completed=0, in_progress=False)

    batch = json.loads(raw)
    application_ids: list[str] = batch["application_ids"]
    dispatched_at = datetime.fromisoformat(batch["dispatched_at"])
    if not application_ids:
        return RerunAtsStatusResponse(total_queued=0, completed=0, in_progress=False)

    with db_cursor() as (conn, cur):
        placeholders = ",".join("?" for _ in application_ids)
        cur.execute(
            f"SELECT id, ats_evaluated_at FROM Applications WHERE id IN ({placeholders})",
            *application_ids,
        )
        rows = cur.fetchall()

        completed = 0
        for r in rows:
            application_id, evaluated_at = str(r[0]), r[1]
            if evaluated_at is not None:
                val = evaluated_at if evaluated_at.tzinfo else evaluated_at.replace(tzinfo=timezone.utc)
                if val >= dispatched_at:
                    completed += 1
                    continue
            if is_excluded_from_ats_rerun(cur, application_id, job_id):
                completed += 1

    total = len(application_ids)
    return RerunAtsStatusResponse(total_queued=total, completed=completed, in_progress=completed < total)


def get_interview_qa(interview_id: str) -> list[EvaluationQuestionItem]:
    with db_cursor() as (conn, cur):
        cur.execute(
            """
            SELECT q.question_text, iq.candidate_answer, iq.score, iq.notes
            FROM InterviewQuestions iq
            JOIN Questions q ON q.id = iq.question_id
            WHERE iq.interview_id = ?
            ORDER BY q.created_at
            """,
            interview_id,
        )
        return [
            EvaluationQuestionItem(
                question_text=str(r[0]),
                candidate_answer=str(r[1]) if r[1] else None,
                score=int(r[2]) if r[2] is not None else None,
                notes=str(r[3]) if r[3] else None,
            )
            for r in cur.fetchall()
        ]
