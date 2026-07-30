"""Celery ETA dispatch helpers for `Interviews.scheduled_at`.

`scheduled_at` is always stored as the recruiter's LOCAL wall-clock time, alongside
`scheduled_timezone` (an IANA zone name); it is never converted to or stored as UTC.
The only place a UTC value is ever computed is transiently, in-memory, to hand Celery
an absolute `eta` for `run_scheduled_interview_task` — Celery itself has no notion of
"local time", so this conversion is unavoidable, but nothing derived from it is
persisted back to the DB.

The recruiter now schedules interviews by creating the event directly in their own
Google Calendar (see JobPostStats.tsx) — this module no longer picks slots, validates
working hours, or talks to the Google API itself. `app/api/endpoints/google_calendar.py`'s
webhook handler is what actually decides an interview's schedule, using the two
functions kept here to (re)dispatch the same Celery ETA task that always drove the AI
agent joining a scheduled interview's room.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# How much earlier than the recruiter-picked start time the Celery task actually
# fires — gives the agent time to fetch the job/CV context, create the room, and
# connect before the candidate's scheduled time arrives, instead of doing all of that
# live in front of a waiting candidate. Kept well under the join-window buffer in
# settings.SCHEDULED_INTERVIEW_JOIN_WINDOW_MINUTES (see room_connection.py) so it never
# eats into the candidate's actual no-show grace period.
EARLY_DISPATCH_SECONDS = 30


def _compute_eta_utc(local_dt: datetime, timezone: str) -> datetime:
    return local_dt.replace(tzinfo=ZoneInfo(timezone)).astimezone(ZoneInfo("UTC"))


def _dispatch_schedule_task(interview_id: str, local_dt: datetime, timezone: str) -> str:
    # Deferred import: interview_scheduling_tasks imports this module's functions
    # indirectly via room_connection — a top-level import here would cycle.
    from app.tasks.interview_scheduling_tasks import run_scheduled_interview_task

    eta_utc = _compute_eta_utc(local_dt, timezone) - timedelta(seconds=EARLY_DISPATCH_SECONDS)
    result = run_scheduled_interview_task.apply_async(args=[interview_id], eta=eta_utc)
    return result.id


MIN_SCHEDULE_BUFFER_MINUTES = 2
"""Minimum lead time required between "now" and a recruiter-picked interview start
time — guards against a Calendar event whose start is so close to "now" that the
early-dispatched Celery task/agent pre-join wouldn't have meaningful time to run
before it (see EARLY_DISPATCH_SECONDS above), or one that's already in progress or
over by the time the webhook processes it."""


def validate_schedule_time(local_dt: datetime, end_dt: datetime | None = None) -> str | None:
    """Returns a human-readable rejection reason if `local_dt` (and optionally
    `end_dt`) isn't an acceptable interview start time right now, or None if it's
    fine to schedule. Compares against a naive datetime.now() — same wall-clock
    convention as scheduled_at/scheduled_timezone elsewhere in this module (see
    module docstring): both are the recruiter's own local time, never converted to
    UTC before this comparison."""
    now_local = datetime.now()
    if local_dt < now_local:
        return f"start time {local_dt} is already in the past (now={now_local})"
    if end_dt is not None and end_dt < now_local:
        return f"end time {end_dt} is already in the past (now={now_local})"
    if local_dt < now_local + timedelta(minutes=MIN_SCHEDULE_BUFFER_MINUTES):
        return (
            f"start time {local_dt} is less than {MIN_SCHEDULE_BUFFER_MINUTES} "
            f"minute(s) from now ({now_local})"
        )
    return None


def revoke_pending_schedule_task(schedule_task_id: str | None) -> None:
    """Cancels a previously-dispatched ETA task — called before dispatching a new one
    on reschedule, so a stale task can never fire the agent into a room at the old time."""
    if not schedule_task_id:
        return
    try:
        from app.celery_app import celery_app
        celery_app.control.revoke(schedule_task_id)
    except Exception:
        logger.exception("scheduling_service: failed to revoke task_id=%s", schedule_task_id)


TOKEN_TTL_BUFFER_SECONDS = 300  # 5 minutes


def compute_token_ttl_seconds(expires_at_local: datetime, timezone: str) -> int:
    """Converts Interviews.livekit_token_expires_at (naive local wall-clock, same
    convention as scheduled_at) into a TTL in seconds relative to now — used wherever
    an agent/candidate LiveKit token is actually minted (room_connection.py), so a
    token doesn't outlive the interview it belongs to (or die from the SDK's default
    6-hour TTL before an interview scheduled further out even starts).

    Adds TOKEN_TTL_BUFFER_SECONDS on top of the stored expiry so the token stays valid
    a little past the interview's expected end — e.g. if wrap-up/scoring runs a bit
    long, the room connection doesn't get cut off mid-flow. Floors at 60s so a token
    minted right at the boundary still works long enough to connect."""
    remaining = (_compute_eta_utc(expires_at_local, timezone) - datetime.now(ZoneInfo("UTC"))).total_seconds()
    return max(60, int(remaining) + TOKEN_TTL_BUFFER_SECONDS)
