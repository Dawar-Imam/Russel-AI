"""Google Calendar integration for recruiter-scheduled interviews.

Deliberately isolated behind this small function surface (connect/watch/get/cancel) so
callers never touch the Google API client directly — if the calendar provider ever
changes, only this file changes.

The backend no longer creates or updates Calendar events itself — the recruiter builds
the interview event by hand in their own Google Calendar (see JobPostStats.tsx opening
calendar.google.com with a prefilled description). This module's job is now limited to:
OAuth connect, registering a push-notification "watch" channel on the recruiter's
calendar so Google tells us when something changes (`watch_calendar`), and fetching a
single event by id once the webhook handler (`google_calendar.py`) has decided which one
changed (`get_event`). `cancel_event` is kept for a future recruiter-initiated cancel
flow — best-effort (log-and-continue), same reasoning as before: a recruiter shouldn't
get stuck because Calendar cleanup failed.
"""
import logging
import uuid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.database import db_cursor

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarError(Exception):
    """Raised whenever an interview's Google Calendar event could not be created,
    updated, or the recruiter's credentials could not be resolved/refreshed. Always
    carries a recruiter-facing message — scheduling_service.py surfaces this directly
    as the HTTP error, so keep it human-readable, not a raw stack trace."""


def _flow(state: str | None = None) -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=_SCOPES,
        state=state,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        autogenerate_code_verifier=False,
    )


def get_authorization_url(recruiter_id: str) -> str:
    """Returns the Google consent-screen URL. `recruiter_id` is passed through as OAuth
    `state` so the callback knows which recruiter to attach the resulting token to,
    without needing a server-side session."""
    flow = _flow(state=recruiter_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # forces a refresh_token on every connect, not just the first
    )
    logger.info("google_calendar: generated authorization URL for recruiter=%s", recruiter_id)
    return auth_url


def handle_oauth_callback(code: str, recruiter_id: str) -> None:
    """Exchanges the authorization code for tokens and stores the refresh token on
    RecruiterProfiles. Raises on failure — the callback endpoint surfaces this as an
    error page, since a failed connect here means the recruiter would otherwise be
    silently left in a "connected" state that isn't real."""
    logger.info("google_calendar: exchanging authorization code for tokens, recruiter=%s", recruiter_id)
    flow = _flow(state=recruiter_id)
    try:
        flow.fetch_token(code=code)
    except Exception:
        logger.exception("google_calendar: token exchange failed for recruiter=%s", recruiter_id)
        raise
    refresh_token = flow.credentials.refresh_token
    logger.info(
        "google_calendar: token exchange succeeded for recruiter=%s (has_refresh_token=%s, scopes=%s)",
        recruiter_id, bool(refresh_token), flow.credentials.scopes,
    )
    if not refresh_token:
        raise ValueError("Google did not return a refresh token — try disconnecting and reconnecting.")

    with db_cursor() as (conn, cur):
        cur.execute(
            "UPDATE RecruiterProfiles SET google_refresh_token = ?, google_calendar_connected = 1 WHERE id = ?",
            refresh_token,
            recruiter_id,
        )
        conn.commit()

    if settings.GOOGLE_WEBHOOK_URL:
        logger.info(
            "google_calendar: GOOGLE_WEBHOOK_URL=%s configured, invoking watch_calendar for recruiter=%s",
            settings.GOOGLE_WEBHOOK_URL, recruiter_id,
        )
        try:
            watch_calendar(recruiter_id)
        except GoogleCalendarError:
            # Connect itself succeeded (refresh token stored) — don't fail the whole
            # OAuth flow over the webhook registration. Scheduling still works, just
            # without live sync until the recruiter reconnects.
            logger.exception("google_calendar: connected but failed to register watch for recruiter=%s", recruiter_id)
    else:
        # This is the most common reason google_watch_channel_id/resource_id end up
        # NULL on RecruiterProfiles after a connect — watch_calendar() is never even
        # called. GOOGLE_WEBHOOK_URL must be a real HTTPS URL Google can reach (a
        # tunnel like ngrok/cloudflared in local dev, or the deployed domain) —
        # http://localhost:... will never work, Google will reject or silently never
        # deliver to it.
        logger.warning(
            "google_calendar: GOOGLE_WEBHOOK_URL is not set — skipping watch registration for recruiter=%s. "
            "google_watch_channel_id/resource_id will stay NULL and the webhook will never receive events for "
            "this recruiter until GOOGLE_WEBHOOK_URL is configured and they reconnect Calendar.",
            recruiter_id,
        )
    logger.info("google_calendar: recruiter=%s successfully connected Google Calendar", recruiter_id)


def is_calendar_connected(recruiter_id: str) -> bool:
    with db_cursor() as (conn, cur):
        cur.execute("SELECT google_calendar_connected FROM RecruiterProfiles WHERE id = ?", recruiter_id)
        row = cur.fetchone()
    return bool(row and row[0])


def get_recruiter_id_by_watch_channel(channel_id: str) -> str | None:
    """Resolves a webhook's `X-Goog-Channel-ID` header back to the recruiter who owns
    that watch channel — the webhook handler uses this to verify a notification
    actually belongs to a recruiter we registered, before trusting anything else in
    the request."""
    with db_cursor() as (conn, cur):
        cur.execute("SELECT id FROM RecruiterProfiles WHERE google_watch_channel_id = ?", channel_id)
        row = cur.fetchone()
    return str(row[0]) if row else None


def _get_credentials(recruiter_id: str) -> Credentials:
    """Raises GoogleCalendarError (never returns None) — every caller in this module
    needs working credentials to do anything, so a missing/unrefreshable token is
    always a hard failure, not a silently-skipped step."""
    with db_cursor() as (conn, cur):
        cur.execute("SELECT google_refresh_token FROM RecruiterProfiles WHERE id = ?", recruiter_id)
        row = cur.fetchone()
    if not row or not row[0]:
        logger.warning("google_calendar: recruiter=%s has not connected Google Calendar", recruiter_id)
        raise GoogleCalendarError(
            "You haven't connected Google Calendar yet — connect it before scheduling an interview."
        )

    creds = Credentials(
        token=None,
        refresh_token=str(row[0]),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=_SCOPES,
    )
    try:
        creds.refresh(Request())
    except Exception as exc:
        logger.exception("google_calendar: failed to refresh access token for recruiter=%s", recruiter_id)
        raise GoogleCalendarError(
            "Your Google Calendar connection has expired or been revoked — reconnect it and try again."
        ) from exc
    return creds


def _calendar_id_for_logging(service, recruiter_id: str) -> str:
    """Best-effort only — used purely to make log lines identify which actual Google
    account/calendar an event was written to, never load-bearing for the event itself
    (the API call always targets calendarId="primary" regardless of this lookup)."""
    try:
        return str(service.calendars().get(calendarId="primary").execute().get("id"))
    except Exception:
        return f"<unknown calendar for recruiter={recruiter_id}>"


def watch_calendar(recruiter_id: str) -> None:
    """Registers a push-notification channel on the recruiter's primary calendar so
    Google POSTs to settings.GOOGLE_WEBHOOK_URL whenever an event changes. Called once,
    right after handle_oauth_callback succeeds. Channels expire (~7 days, whatever
    Google returns) — there is no renewal job yet; a lapsed channel just stops
    delivering webhooks until the recruiter reconnects Calendar.

    Raises GoogleCalendarError on failure, same as the rest of this module — a
    recruiter who just connected Calendar should see an error immediately if we can't
    also register the watch, rather than silently never receiving scheduling updates.
    """
    creds = _get_credentials(recruiter_id)
    channel_id = str(uuid.uuid4())
    logger.info("google_calendar: watch created -> requesting watch channel=%s for recruiter=%s", channel_id, recruiter_id)
    try:
        service = build("calendar", "v3", credentials=creds)
        body = {"id": channel_id, "type": "web_hook", "address": settings.GOOGLE_WEBHOOK_URL}
        response = service.events().watch(calendarId="primary", body=body).execute()
        resource_id = response.get("resourceId")
        expiration_ms = response.get("expiration")
        logger.info(
            "google_calendar: Google returned channel_id=%s resource_id=%s for recruiter=%s (expires_ms=%s)",
            channel_id, resource_id, recruiter_id, expiration_ms,
        )
        with db_cursor() as (conn, cur):
            cur.execute(
                """UPDATE RecruiterProfiles
                   SET google_watch_channel_id = ?, google_watch_resource_id = ?,
                       google_watch_expires_at = DATEADD(SECOND, ?, '19700101')
                   WHERE id = ?""",
                channel_id,
                resource_id,
                int(expiration_ms) // 1000 if expiration_ms else None,
                recruiter_id,
            )
            rows_updated = cur.rowcount
            conn.commit()
        if rows_updated != 1:
            # Should be impossible (recruiter_id came from a row we already loaded
            # credentials for above) — logged loudly rather than silently trusting
            # the UPDATE, since a 0-row update would leave the channel registered
            # with Google but never persisted, so the webhook could never match it.
            logger.error(
                "google_calendar: DB update FAILED to persist watch fields for recruiter=%s "
                "(rowcount=%d, expected 1) — channel_id=%s resource_id=%s registered with Google but NOT saved",
                recruiter_id, rows_updated, channel_id, resource_id,
            )
        else:
            logger.info(
                "google_calendar: DB update succeeded -> persisted channel_id=%s resource_id=%s on "
                "RecruiterProfiles for recruiter=%s",
                channel_id, resource_id, recruiter_id,
            )
    except HttpError as exc:
        logger.exception("google_calendar: API error registering watch for recruiter=%s", recruiter_id)
        raise GoogleCalendarError(f"Google Calendar rejected the watch request: {exc.reason if hasattr(exc, 'reason') else exc}") from exc
    except Exception as exc:
        logger.exception("google_calendar: unexpected error registering watch for recruiter=%s", recruiter_id)
        raise GoogleCalendarError("Failed to register the Google Calendar webhook — please try again.") from exc


def get_event(recruiter_id: str, event_id: str) -> dict:
    """Fetches a single event by id from the recruiter's primary calendar — used by the
    webhook handler once it has picked a candidate event to check. Raises
    GoogleCalendarError on failure (not connected, revoked token, event not found)."""
    creds = _get_credentials(recruiter_id)
    try:
        service = build("calendar", "v3", credentials=creds)
        return service.events().get(calendarId="primary", eventId=event_id).execute()
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar rejected the event lookup: {exc.reason if hasattr(exc, 'reason') else exc}") from exc
    except Exception as exc:
        raise GoogleCalendarError("Failed to fetch the Google Calendar event.") from exc


def list_recent_events(recruiter_id: str, updated_min_iso: str) -> list[dict]:
    """Lists events on the recruiter's primary calendar updated since `updated_min_iso`
    (RFC3339 UTC) — used by the webhook handler instead of a full sync-token-based
    change feed, since Calendar's push notification carries no event data, only
    "something changed". A small bounded time-window list is enough at interview-
    scheduling volume; deliberately not a general sync mechanism."""
    creds = _get_credentials(recruiter_id)
    try:
        service = build("calendar", "v3", credentials=creds)
        response = service.events().list(
            calendarId="primary", updatedMin=updated_min_iso, singleEvents=True, showDeleted=True,
        ).execute()
        return response.get("items", [])
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar rejected the events list: {exc.reason if hasattr(exc, 'reason') else exc}") from exc
    except Exception as exc:
        raise GoogleCalendarError("Failed to list recent Google Calendar events.") from exc


def cancel_event(recruiter_id: str, event_id: str) -> None:
    """Best-effort (log-and-continue), unlike create/update above — a recruiter
    cancelling/deleting an interview on our side should never get stuck because
    Calendar cleanup failed; a stale event left behind is a minor annoyance, not a
    data-integrity problem the way a phantom "scheduled" interview would be."""
    try:
        creds = _get_credentials(recruiter_id)
        service = build("calendar", "v3", credentials=creds)
        calendar_id = _calendar_id_for_logging(service, recruiter_id)
        logger.info("google_calendar: cancelling event=%s for recruiter=%s calendar=%s", event_id, recruiter_id, calendar_id)
        service.events().delete(calendarId="primary", eventId=event_id, sendUpdates="all").execute()
        logger.info("google_calendar: cancelled event=%s for recruiter=%s", event_id, recruiter_id)
    except (HttpError, GoogleCalendarError, Exception):
        logger.exception("google_calendar: failed to cancel event=%s for recruiter=%s", event_id, recruiter_id)
