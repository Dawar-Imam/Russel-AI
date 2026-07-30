import asyncio
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.services import interview_service, scheduling_service
from app.services.events import publish_ats_completed, publish_job_update
from app.services.google_calendar_service import (
    GoogleCalendarError,
    get_authorization_url,
    get_recruiter_id_by_watch_channel,
    handle_oauth_callback,
    is_calendar_connected,
    list_recent_events,
)
from app.services.interview_service import InterviewNotDeletableError

logger = logging.getLogger(__name__)

router = APIRouter()

# JobPostStats.tsx puts the candidate's interview-room join link
# (`{FRONTEND_URL}/interview-room/{interview_id}`) in the Calendar event description
# when the recruiter opens Google Calendar to schedule an interview — the only signal
# the webhook handler uses to match an arbitrary Calendar event back to an interview
# (see module docstring in google_calendar_service.py for why: no fuzzy attendee/time
# matching).
_INTERVIEW_ID_RE = re.compile(r"/interview-room/([0-9a-fA-F-]{36})")
# How far back to look for changed events on each webhook ping — the push notification
# itself carries no event data, only "something changed on this calendar".
_LOOKBACK_MINUTES = 10
# Default oral-round duration when InterviewRounds.time_limit_minutes wasn't set by the
# recruiter — mirrors interview_service._limit_seconds' own oral fallback.
_DEFAULT_ORAL_DURATION_MINUTES = settings.INTERVIEW_DURATION_MINUTES
# Extra time past the interview's expected end before its LiveKit token expires —
# absorbs the interview running slightly long or starting a few minutes late.
_TOKEN_EXPIRY_BUFFER_MINUTES = 5


@router.get("/status")
def status(recruiter_id: str = Query(...)) -> dict:
    """Whether this recruiter has completed the Google Calendar OAuth connect flow —
    the Job Stats page checks this before letting the recruiter open Google Calendar to
    schedule an interview."""
    try:
        return {"connected": is_calendar_connected(recruiter_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/connect")
def connect(recruiter_id: str = Query(...)) -> dict:
    """Returns the Google consent-screen URL — the recruiter dashboard opens this in a
    new tab/redirect to start the one-time "Connect Google Calendar" flow."""
    try:
        return {"authorization_url": get_authorization_url(recruiter_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/callback")
def callback(code: str = Query(...), state: str = Query(...)) -> RedirectResponse:
    """Google redirects here after the recruiter grants (or denies) consent. `state`
    carries the recruiter_id through, unchanged, from connect() above.

    Redirects back to /auth, not /recruiter-dashboard: the only place that starts this
    flow now is the recruiter signup screen (Auth.tsx), before the recruiter has ever
    signed in — /recruiter-dashboard is a ProtectedRoute that would just bounce them
    straight back to "/" with no sessionStorage set yet."""
    logger.info("google_calendar callback: received code for recruiter(state)=%s", state)
    try:
        handle_oauth_callback(code, recruiter_id=state)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth?google_calendar=connected")
    except Exception:
        logger.exception("google_calendar callback: failed to complete OAuth for recruiter(state)=%s", state)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/auth?google_calendar=error")


def _parse_event_datetime(event: dict) -> tuple[datetime, str] | None:
    """Naive local wall-clock datetime + IANA timezone name, matching what
    Interviews.scheduled_at/scheduled_timezone store — mirrors how scheduling_service
    persists a recruiter-picked time. None for all-day events (no time component),
    which aren't valid interview slots."""
    start = event.get("start", {})
    dt_str = start.get("dateTime")
    if not dt_str:
        return None
    dt = datetime.fromisoformat(dt_str)
    return dt.replace(tzinfo=None), start.get("timeZone") or settings.DEFAULT_SCHEDULING_TIMEZONE


def _parse_event_end_datetime(event: dict) -> datetime | None:
    """Same wall-clock extraction as _parse_event_datetime, but for the event's end
    time — used only for past-time validation (scheduling_service.validate_schedule_time);
    not persisted anywhere (round duration still comes from
    InterviewRounds.time_limit_minutes, unrelated to the Calendar event's own end)."""
    end = event.get("end", {})
    dt_str = end.get("dateTime")
    if not dt_str:
        return None
    return datetime.fromisoformat(dt_str).replace(tzinfo=None)


def _handle_cancelled_event(recruiter_id: str, event_id: str | None) -> None:
    """A cancelled/deleted event carries no description (Google strips it), so this
    can't use the join-link marker — it matches purely on `google_event_id`, which was
    persisted on the interview the first time this event was matched (see
    set_interview_schedule above). Mirrors delete_interview_round's own guards: a round
    that already started/finished is left alone even if its Calendar event gets deleted
    well after the fact."""
    if not event_id:
        return
    interview_id = interview_service.get_interview_by_google_event_id(recruiter_id, event_id)
    if not interview_id:
        logger.info("google_calendar webhook: cancelled event=%s has no matching interview, skipping", event_id)
        return
    try:
        ctx = interview_service.delete_interview_round(interview_id)
    except InterviewNotDeletableError as exc:
        logger.info("google_calendar webhook: cancelled event=%s ignored -> %s", event_id, exc)
        return
    except ValueError:
        logger.warning("google_calendar webhook: cancelled event=%s matched interview=%s but it was already gone", event_id, interview_id)
        return

    scheduling_service.revoke_pending_schedule_task(ctx["schedule_task_id"])
    logger.info(
        "google_calendar webhook: cancelled event=%s -> unscheduled interview=%s (recruiter cancelled the Calendar event)",
        event_id, interview_id,
    )
    try:
        asyncio.run(publish_job_update(
            ctx["job_posting_id"],
            {"event": "interview_unscheduled", "interview_id": interview_id},
        ))
    except Exception:
        logger.exception("google_calendar webhook: failed to publish interview_unscheduled for job_id=%s", ctx["job_posting_id"])


@router.post("/webhook")
def calendar_webhook(request: Request) -> Response:
    """Google Calendar push notification target (registered by
    google_calendar_service.watch_calendar). Carries no event body — only headers
    telling us a calendar changed — so this fetches the small set of recently-updated
    events, matches any whose description carries our interview-room join link (see
    JobPostStats.tsx), and updates that interview's schedule. Also handles the
    cancelled/deleted case (_handle_cancelled_event), matched by google_event_id
    instead since Google strips the description from cancelled events.

    Always returns 200: Google retries with backoff on non-2xx, and none of the
    failure modes here (unknown channel, no matching interview, a transient Calendar
    API error) are things a retry would fix — logging and moving on is correct.
    """
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    logger.info(
        "google_calendar webhook: received — channel_id=%s resource_id=%s resource_state=%s",
        channel_id, resource_id, resource_state,
    )

    if not channel_id:
        logger.warning("google_calendar webhook: no X-Goog-Channel-ID header, ignoring")
        return Response(status_code=200)

    # Ownership check: only process notifications for a channel we actually
    # registered, mapped back to the recruiter it belongs to. Reject (log + 200,
    # never process) anything that doesn't match a known channel.
    recruiter_id = get_recruiter_id_by_watch_channel(channel_id)
    if not recruiter_id:
        logger.warning("google_calendar webhook: unknown channel_id=%s, rejecting", channel_id)
        return Response(status_code=200)
    logger.info("google_calendar webhook: channel matched -> recruiter=%s", recruiter_id)

    if resource_state == "sync":
        # One-time confirmation sent when the channel is first created — no event data.
        logger.info("google_calendar webhook: resource_state=sync (channel creation ack), nothing to process")
        return Response(status_code=200)

    updated_min = (datetime.utcnow() - timedelta(minutes=_LOOKBACK_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        events = list_recent_events(recruiter_id, updated_min)
    except GoogleCalendarError:
        logger.exception("google_calendar webhook: failed to list recent events for recruiter=%s", recruiter_id)
        return Response(status_code=200)
    logger.info(
        "google_calendar webhook: event fetched -> %d event(s) updated since %s for recruiter=%s",
        len(events), updated_min, recruiter_id,
    )

    for event in events:
        event_id = event.get("id")
        if event.get("status") == "cancelled":
            _handle_cancelled_event(recruiter_id, event_id)
            continue

        match = _INTERVIEW_ID_RE.search(event.get("description") or "")
        if not match:
            logger.info("google_calendar webhook: event=%s has no interview-room join link in its description, skipping", event_id)
            continue
        interview_id = match.group(1)
        logger.info("google_calendar webhook: interview matched -> event=%s interview_id=%s", event_id, interview_id)

        ctx = interview_service.get_schedule_context(interview_id)
        if ctx is None:
            logger.warning("google_calendar webhook: event=%s references unknown interview=%s, skipping", event_id, interview_id)
            continue
        if ctx["recruiter_id"] != recruiter_id:
            logger.warning(
                "google_calendar webhook: interview=%s belongs to recruiter=%s, not channel owner=%s — ignoring",
                interview_id, ctx["recruiter_id"], recruiter_id,
            )
            continue

        parsed = _parse_event_datetime(event)
        if parsed is None:
            logger.info("google_calendar webhook: event=%s has no dateTime (all-day event), skipping", event_id)
            continue
        local_dt, timezone = parsed

        # Reject a schedule whose start/end is already in the past, or whose start is
        # too close to "now" to give the early-dispatched Celery task/agent pre-join
        # meaningful lead time — see scheduling_service.MIN_SCHEDULE_BUFFER_MINUTES.
        end_dt = _parse_event_end_datetime(event)
        rejection_reason = scheduling_service.validate_schedule_time(local_dt, end_dt)
        if rejection_reason:
            logger.warning(
                "google_calendar webhook: event=%s for interview=%s rejected -> %s",
                event_id, interview_id, rejection_reason,
            )
            continue

        # Idempotency: a burst of webhook pings for the same underlying change
        # shouldn't repeatedly revoke/redispatch the Celery ETA task.
        if ctx["google_event_id"] == event_id and ctx["scheduled_at"] == local_dt:
            logger.info("google_calendar webhook: interview=%s already up to date, skipping re-dispatch", interview_id)
            continue

        scheduling_service.revoke_pending_schedule_task(ctx["schedule_task_id"])
        task_id = scheduling_service._dispatch_schedule_task(interview_id, local_dt, timezone)
        logger.info(
            "google_calendar webhook: dispatched Celery task_id=%s for interview=%s -> scheduled_at=%s %s (fires ~%ds early)",
            task_id, interview_id, local_dt, timezone, scheduling_service.EARLY_DISPATCH_SECONDS,
        )
        interview_service.set_interview_schedule(interview_id, local_dt, timezone, event_id, task_id)
        logger.info(
            "google_calendar webhook: DB updated -> interview=%s scheduled_at=%s timezone=%s (from event=%s)",
            interview_id, local_dt, timezone, event_id,
        )

        # LiveKit token TTL = time until the interview starts + its duration + a small
        # buffer — computed here (once we know the recruiter-picked start time) and
        # stored so a token minted later (agent pre-join, candidate join-click) expires
        # right after the interview should be over instead of using the SDK's default
        # 6-hour TTL. See scheduling_service.compute_token_ttl_seconds.
        duration_minutes = ctx["time_limit_minutes"] or _DEFAULT_ORAL_DURATION_MINUTES
        expires_at_local = local_dt + timedelta(minutes=duration_minutes + _TOKEN_EXPIRY_BUFFER_MINUTES)
        interview_service.set_interview_livekit_expiry(interview_id, expires_at_local)

        try:
            # publish_ats_completed is really just "publish a domain event on the
            # per-application WS channel" — the name is ATS-specific but the bus
            # itself (Redis pub/sub -> ws.py's ConnectionManager) is payload-agnostic,
            # so it's reused here rather than standing up a second channel.
            asyncio.run(publish_ats_completed(
                ctx["application_id"],
                {
                    "event": "interview_scheduled",
                    "application_id": ctx["application_id"],
                    "interview_id": interview_id,
                    "scheduled_at": local_dt.isoformat(),
                    "scheduled_timezone": timezone,
                },
            ))
            logger.info(
                "google_calendar webhook: frontend notification sent -> application_id=%s interview_id=%s",
                ctx["application_id"], interview_id,
            )
        except Exception:
            logger.exception(
                "google_calendar webhook: failed to publish interview_scheduled event for application_id=%s",
                ctx["application_id"],
            )

        try:
            # Recruiter-side counterpart of the candidate notification above — same
            # event, delivered on the job-keyed WS channel JobPostStats listens on
            # instead of the application-keyed one ApplicationProgress listens on.
            asyncio.run(publish_job_update(
                ctx["job_posting_id"],
                {
                    "event": "interview_scheduled",
                    "interview_id": interview_id,
                    "scheduled_at": local_dt.isoformat(),
                    "scheduled_timezone": timezone,
                },
            ))
        except Exception:
            logger.exception(
                "google_calendar webhook: failed to publish interview_scheduled job_update for job_id=%s",
                ctx["job_posting_id"],
            )

    return Response(status_code=200)
