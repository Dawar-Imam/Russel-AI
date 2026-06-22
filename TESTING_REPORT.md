# Russel-AI — End-to-End Testing & Validation Report

**Date:** 2026-06-18  
**Branch:** dev  
**Scope:** Full static audit of backend (FastAPI), frontend (React/TypeScript), and
their integration path. The database is SQL Server via pyodbc (raw connections, no ORM
models in use). AI agent layer was reviewed for integration correctness; live AI calls
were not exercised.

---

## Legend

| Severity | Meaning |
|----------|---------|
| **CRITICAL** | Data corruption, authentication bypass, security vulnerability exploitable without auth |
| **HIGH** | Incorrect behavior visible in production, validation bypassed at the API level |
| **MEDIUM** | Edge-case failures, inconsistencies between frontend and backend |
| **LOW** | UX problems, minor gaps, code hygiene |

`FIXED` — applied in this session.  
`NOT FIXED` — architectural decision or out-of-scope; described fully so it can be tracked.

---

## 1. Authentication Flow

### BUG-AUTH-01 — Timing Attack in Password Verification  
**Severity:** CRITICAL | **Status:** FIXED  
**File:** `backend/app/services/auth_service.py:23`

`_verify_password` compared PBKDF2 digests with `==`, which allows a timing side-channel
attack to leak the hash.

```python
# Before
return dk.hex() == dk_hex
# After
return hmac.compare_digest(dk.hex(), dk_hex)
```

---

### BUG-AUTH-02 — No Email Format Validation on Backend  
**Severity:** HIGH | **Status:** FIXED  
**Files:** `backend/app/schemas/auth.py`, `backend/app/api/endpoints/auth.py`

`SigninRequest`, `RecruiterSignupRequest`, and the candidate signup Form endpoint all
accepted any string for `email`. An email like `"notanemail"`, `"@"`, or `""` was
inserted into the `Users` table without error.

Fix: added `@field_validator('email')` with a standard regex to both Pydantic schemas
and the Form-based candidate signup endpoint. Email is also normalised to lowercase.

---

### BUG-AUTH-03 — No Password Minimum-Length Validation on Backend  
**Severity:** HIGH | **Status:** FIXED  
**Files:** `backend/app/schemas/auth.py`, `backend/app/api/endpoints/auth.py`

Any password was accepted (including empty string). Fix: added an 8-character minimum
via `@field_validator('password')` on `RecruiterSignupRequest`, and an inline check in
the candidate signup endpoint.

---

### BUG-AUTH-04 — No Empty-Field Validation on Backend  
**Severity:** HIGH | **Status:** FIXED  
**Files:** `backend/app/schemas/auth.py`, `backend/app/api/endpoints/auth.py`

`RecruiterSignupRequest` accepted whitespace-only strings for `first_name`, `last_name`,
`company_name`, and `designation`. The candidate signup endpoint accepted whitespace-only
`first_name` and `last_name`. Fix: added `@field_validator` / inline strip-and-check on
all required string fields.

---

### BUG-AUTH-05 — Negative `experience_years` Accepted  
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `backend/app/api/endpoints/auth.py`

The candidate signup endpoint accepted `experience_years=-5`. Fix: added
`if experience_years < 0: errors.append(...)` before calling the service.

---

### BUG-AUTH-06 — No CV File-Size Limit  
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `backend/app/api/endpoints/auth.py`

An attacker could upload an arbitrarily large file as `cv`, consuming server memory and
disk. Fix: added a 5 MB cap; requests exceeding it receive HTTP 413.

---

### BUG-AUTH-07 — `candidateId` Not Stored in `sessionStorage` on Candidate Signin  
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `frontend/src/pages/Auth.tsx:117`

Recruiter signin explicitly stores `recruiterId` in `sessionStorage`
(`sessionStorage.setItem('recruiterId', result.recruiter_id)`), but candidate signin
only passes `candidateId` via React Router state. `Jobs.tsx` does persist it on arrival
(`sessionStorage.setItem('candidateId', fromState)`), so this works as long as the
candidate navigates directly from `/auth` → `/jobs`. If the candidate lands on `/jobs`
by any other path (e.g. browser back after revisiting `/auth`), the state is gone and
sessionStorage falls back to the previously stored value — which may be stale.

Recommendation: mirror the recruiter pattern and call
`sessionStorage.setItem('candidateId', result.candidate_id)` immediately on signin
success.

---

### BUG-AUTH-08 — No Logout Mechanism  
**Severity:** LOW | **Status:** NOT FIXED  
**Files:** all frontend pages

There is no sign-out button anywhere. `sessionStorage` entries (`candidateId`,
`recruiterId`) persist for the entire browser session; there is no way to switch
accounts without closing the tab. On the backend, because no JWT/session tokens are
issued, "logout" is purely a client-side concern — but the frontend doesn't implement it.

---

### BUG-AUTH-09 — No JWT / Token-Based Authentication  
**Severity:** CRITICAL | **Status:** NOT FIXED (architectural)  
**Files:** all API endpoints

The authentication system issues no token. After signin, the backend returns raw
`user_id` / `candidate_id` / `recruiter_id`. Every subsequent API call sends these IDs
in the request body or as query parameters with zero server-side verification that the
caller actually owns them. Concrete consequences:

- `GET /api/jobs/mine?recruiter_id=X` — any unauthenticated caller can enumerate any
  recruiter's jobs by guessing/brute-forcing UUIDs.
- `POST /api/jobs` with `{"recruiter_id": "X"}` — anyone can post a job as any
  recruiter.
- `POST /api/applications/apply` with `{"candidate_id": "X"}` — anyone can submit an
  application on behalf of any candidate.
- `POST /api/interviews/{id}/generate-questions` — no ownership check; any caller
  can generate questions for any interview.
- `POST /api/interviews/{id}/score-answers` — any caller can trigger AI scoring for
  any interview.

Recommendation: issue a signed JWT on signin; add an `Authorization: Bearer <token>`
dependency to every protected route; verify the token's `sub` claim matches the
resource being accessed.

---

## 2. Recruiter Job Posting Flow

### BUG-JOB-01 — `job_type` Not Validated as Enum on Backend  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/schemas/jobs.py`

`job_type: str` accepted any arbitrary string (`"xyz"`, `"full time"`, etc.). The
frontend constrained choices to a hardcoded list but nothing enforced this server-side.
Fix: changed the field type to
`Literal['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']`.

---

### BUG-JOB-02 — No Required-Field Validation in `JobPostRequest`  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/schemas/jobs.py`

`designation`, `description`, `location`, and `recruiter_id` accepted empty/whitespace
strings. Fix: added `@field_validator` that strips and rejects empty values; also added
a 200-character cap on `designation`.

---

### BUG-JOB-03 — `salary_range` Accepts Arbitrary Text  
**Severity:** MEDIUM | **Status:** NOT FIXED  
**File:** `backend/app/schemas/jobs.py`

`salary_range` is a free-text field with no format guidance enforced. Values like
`"abc"`, `"negative"`, or `"one million"` are stored as-is. This is intentional
flexibility (freeform salary descriptions), but there is no length cap.

Recommendation: add a `max_length=150` constraint and document the expected format.

---

### BUG-JOB-04 — `expires_at` Accepts Malformed and Past Dates  
**Severity:** MEDIUM | **Status:** NOT FIXED  
**File:** `backend/app/schemas/jobs.py`

`expires_at: str | None` is forwarded directly to SQL with no date parsing or validation.
A value of `"not-a-date"` causes a SQL error that surfaces as 500. A past date is
silently accepted and immediately makes the job invisible to candidates (it falls outside
the `expires_at > GETDATE()` filter added in this session).

Recommendation: parse with `datetime.date.fromisoformat()` in a validator and reject
past dates.

---

### BUG-JOB-05 — Recruiters Can See Any Recruiter's Jobs (No Auth)  
**Severity:** CRITICAL | **Status:** NOT FIXED (depends on BUG-AUTH-09)  
**File:** `backend/app/api/endpoints/jobs.py:17–22`

`GET /api/jobs/mine?recruiter_id=X` passes `recruiter_id` as a plain query parameter.
There is no check that the caller is the recruiter identified by that ID.

---

### BUG-JOB-06 — `InterviewRounds` Not Created When a Job Is Posted  
**Severity:** CRITICAL | **Status:** NOT FIXED  
**File:** `backend/app/services/job_service.py`

`apply_to_job` in `application_service.py` queries
`InterviewRounds WHERE job_posting_id = ?`. If no rounds exist for a job, the application
row is created but no `Interviews` rows are inserted. `get_interview_stages` then returns
an empty `rounds` list and `current_round_id = null`, leaving the "Go To Interview Room"
button permanently disabled.

This is a missing business-logic step: when a recruiter posts a job, the platform must
also create at least one `InterviewRounds` row (linked to an `InterviewRoundTypes` entry)
to make the interview pipeline functional.

---

## 3. Job Browsing

### BUG-BROWSE-01 — Expired Jobs Shown in Public Listing  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/services/job_service.py:88`

`list_jobs()` only filtered `WHERE jp.status = 'active'` but ignored `expires_at`.
Jobs past their expiry date remained visible to all users. Fix: added
`AND (jp.expires_at IS NULL OR jp.expires_at > GETDATE())`.

---

## 4. Candidate Apply Flow

### BUG-APPLY-01 — Recruiters Can Apply to Jobs (No Role Check)  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/services/application_service.py`

`apply_to_job(job_posting_id, candidate_id)` inserted an `Applications` row without
verifying that `candidate_id` maps to a `CandidateProfiles` row. A recruiter could
pass their own profile ID and apply on behalf of a non-existent candidate.

Fix: added `SELECT id FROM CandidateProfiles WHERE id = ?` before insertion; raises
`ValueError` (→ HTTP 400) if not found.

---

### BUG-APPLY-02 — Applying to Inactive or Deleted Job Raises 500  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/services/application_service.py`

If `job_posting_id` referred to a non-existent or inactive job, the subsequent
`INSERT INTO Applications` failed with a foreign-key constraint violation (SQL error)
that surfaced as HTTP 500 with a cryptic ODBC message.

Fix: added an explicit `SELECT` that validates the job exists and is active before
insertion; raises `ValueError` (→ HTTP 400) with a clear message.

---

### BUG-APPLY-03 — `apply` Endpoint Mapped `ValueError` to 500  
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `backend/app/api/endpoints/applications.py`

The `apply` endpoint caught only `Exception` (→ 500). Any `ValueError` raised by the
service layer was returned as a generic server error instead of a 400. Fix: added a
separate `except ValueError` handler that returns HTTP 400.

---

### BUG-APPLY-04 — No Auth Before Apply  
**Severity:** CRITICAL | **Status:** NOT FIXED (depends on BUG-AUTH-09)  
**File:** `backend/app/api/endpoints/applications.py`

An unauthenticated HTTP call to `POST /api/applications/apply` with a valid
`candidate_id` and `job_posting_id` succeeds. The frontend shows a message ("Please
sign in…") only when `candidateId` is empty — this is entirely client-side and trivially
bypassed.

---

## 5. Interview Flow

### BUG-INT-01 — Completed Interview Can Be Re-Scored  
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/services/interview_service.py`

`score_interview_answers` did not check the current interview `status` before running
AI scoring and overwriting the stored scores. A caller could repeatedly score an already-
completed interview, changing its recorded result.

Fix: added a guard at the start of the function that reads `Interviews.status`; if
`'Completed'`, raises `ValueError` (→ HTTP 404 from the existing handler).

---

### BUG-INT-02 — All Interview Endpoints Completely Unprotected  
**Severity:** CRITICAL | **Status:** NOT FIXED (depends on BUG-AUTH-09)  
**Files:** `backend/app/api/endpoints/interviews.py`

All four endpoints (`generate-questions`, `score-answers`, `voice-interview`,
`status-stream`) accept any `interview_id` without verifying the caller owns it. Any
caller who knows (or guesses) a UUID can:
- Read interview questions belonging to another candidate.
- Submit AI-scored answers for another candidate's interview.
- Start a voice session for an interview they don't own.

---

### BUG-INT-03 — Missing Interview-Not-Found Check in `generate-questions`  
**Severity:** MEDIUM | **Status:** NOT FIXED  
**File:** `backend/app/services/interview_service.py:47`

`get_interview_context` raises `ValueError("Interview {id} not found")` when the
`interview_id` doesn't exist. The endpoint correctly maps `ValueError` → 404. However
there is no guard against generating questions for an already-completed interview
(only re-scoring is guarded now). A completed interview could have its questions
regenerated, displacing the stored set.

Recommendation: add a status check in `generate_interview_questions` before the
`if existing: return` early-exit.

---

### BUG-INT-04 — `API_BASE` Hardcoded in InterviewRoom and InterviewStages  
**Severity:** MEDIUM | **Status:** FIXED  
**Files:** `frontend/src/pages/InterviewRoom.tsx:9`,
`frontend/src/pages/InterviewStages.tsx:7`

Both files had `const API_BASE = 'http://localhost:8000'` instead of reading
`VITE_API_URL`. This meant the interview flow would fail in any environment other than
localhost even if the rest of the app was configured correctly via `.env`.

Fix: changed to
`(import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'`
to match the pattern already used in `auth.ts`, `jobs.ts`, and `JobApplyDialog.tsx`.

---

### BUG-INT-05 — Interview Status Case Mismatch  
**Severity:** HIGH | **Status:** FIXED  
**File:** `frontend/src/pages/InterviewStages.tsx:35`

The `allCompleted` expression checked `currentRound?.status === 'completed'` (lowercase)
but the backend inserts `'Completed'` (capitalised) and the service uses
`status = 'Completed'` in all SQL UPDATE statements. The mismatch meant the "All
interview rounds have been completed" message was never shown; instead the "Go To
Interview Room" button was rendered but clicking it navigated to a broken interview
(since the interview was already finished).

Fix: changed string literal to `'Completed'`.

---

## 6. Database Integrity

### BUG-DB-01 — No Transaction Rollback on Partial Signup Failure  
**Severity:** MEDIUM | **Status:** NOT FIXED  
**File:** `backend/app/services/auth_service.py`

If `signup_candidate` inserts `Users` and `CandidateProfiles` successfully but then
throws during the `CandidateSkills` loop (e.g., an invalid `skill_id` triggers a FK
violation), the exception propagates out through the `finally: conn.close()` block.
`pyodbc` with `autocommit=False` (the default) does roll back implicitly when the
connection is closed without a commit, so data integrity is preserved — but there is no
explicit `conn.rollback()` call, making the intent unclear and fragile if the connection
configuration ever changes.

Recommendation: add an explicit `try/except … conn.rollback(); raise` block around the
mutation sequence.

---

### BUG-DB-02 — Invalid `skill_id` or `job_role_id` Surfaces as HTTP 500  
**Severity:** MEDIUM | **Status:** NOT FIXED  
**Files:** `backend/app/services/auth_service.py`,
`backend/app/services/job_service.py`

If a client submits a `skill_id` that doesn't exist in `SkillSets`, the
`INSERT INTO CandidateSkills` raises an ODBC FK constraint error (SQL error 547). This
surfaces as HTTP 500 with the raw ODBC message. Similarly for an invalid `job_role_id`
in `JobPostRequest`.

Recommendation: validate IDs against the DB before the INSERT (a single
`SELECT id FROM SkillSets WHERE id IN (…)` is sufficient), and raise `ValueError` with
a human-readable message.

---

### BUG-DB-03 — Duplicate Company Created per Recruiter Signup  
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `backend/app/services/auth_service.py:219–226`

Every recruiter signup creates a new `Companies` row, even if a company with the same
name already exists. Two recruiters from "Acme Corp" will have two separate company
entries, breaking any reporting or company-level deduplication.

Recommendation: upsert (SELECT then INSERT if not found) on `Companies.name`, or use a
unique constraint and `MERGE`/`INSERT … WHERE NOT EXISTS`.

---

## 7. General Validation

### BUG-VAL-01 — No Route Protection on Frontend  
**Severity:** HIGH | **Status:** NOT FIXED  
**File:** `frontend/src/App.tsx`

There are no protected routes in the router. A user can navigate directly to
`/recruiter-dashboard` or `/interview-stages/:id` without authentication. The
`RecruiterDashboard` component does redirect if `recruiterId` is empty, but this is
a client-side check only.

---

### BUG-VAL-02 — Missing 404 Catch-All Route  
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `frontend/src/App.tsx`

No `<Route path="*">` catch-all is defined. Navigating to an unknown path renders a
blank page with no feedback.

---

### BUG-VAL-03 — `skill_ids` Parsing Silently Drops Non-Integer Values  
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `backend/app/api/endpoints/auth.py:29`

```python
ids = [int(x.strip()) for x in skill_ids.split(",") if x.strip()]
```

If a client sends `skill_ids="1,abc,3"`, the `int("abc")` raises `ValueError`, caught
by the outer `except ValueError` and returned as HTTP 400. This is the correct outcome,
but the error message is the raw Python exception text ("invalid literal for int()
with base 10: 'abc'") rather than a user-friendly message.

---

### BUG-VAL-04 — Result Not Surfaced on Interview Results Page  
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `frontend/src/pages/InterviewRoom.tsx`

The `score-answers` API response includes a `result` field (`"Pass"` or `"Fail"`), but
the results screen only shows the numeric `overall_score`. The pass/fail verdict is
never shown to the candidate.

---

## Summary Table

| ID | Area | Severity | Status |
|----|------|----------|--------|
| BUG-AUTH-01 | Auth | CRITICAL | **FIXED** |
| BUG-AUTH-02 | Auth | HIGH | **FIXED** |
| BUG-AUTH-03 | Auth | HIGH | **FIXED** |
| BUG-AUTH-04 | Auth | HIGH | **FIXED** |
| BUG-AUTH-05 | Auth | MEDIUM | **FIXED** |
| BUG-AUTH-06 | Auth | MEDIUM | **FIXED** |
| BUG-AUTH-07 | Auth | LOW | NOT FIXED |
| BUG-AUTH-08 | Auth | LOW | NOT FIXED |
| BUG-AUTH-09 | Auth | CRITICAL | NOT FIXED |
| BUG-JOB-01 | Jobs | HIGH | **FIXED** |
| BUG-JOB-02 | Jobs | HIGH | **FIXED** |
| BUG-JOB-03 | Jobs | MEDIUM | NOT FIXED |
| BUG-JOB-04 | Jobs | MEDIUM | NOT FIXED |
| BUG-JOB-05 | Jobs | CRITICAL | NOT FIXED |
| BUG-JOB-06 | Jobs | CRITICAL | NOT FIXED |
| BUG-BROWSE-01 | Browse | HIGH | **FIXED** |
| BUG-APPLY-01 | Apply | HIGH | **FIXED** |
| BUG-APPLY-02 | Apply | HIGH | **FIXED** |
| BUG-APPLY-03 | Apply | MEDIUM | **FIXED** |
| BUG-APPLY-04 | Apply | CRITICAL | NOT FIXED |
| BUG-INT-01 | Interview | HIGH | **FIXED** |
| BUG-INT-02 | Interview | CRITICAL | NOT FIXED |
| BUG-INT-03 | Interview | MEDIUM | NOT FIXED |
| BUG-INT-04 | Interview | MEDIUM | **FIXED** |
| BUG-INT-05 | Interview | HIGH | **FIXED** |
| BUG-DB-01 | DB | MEDIUM | NOT FIXED |
| BUG-DB-02 | DB | MEDIUM | NOT FIXED |
| BUG-DB-03 | DB | LOW | NOT FIXED |
| BUG-VAL-01 | Validation | HIGH | NOT FIXED |
| BUG-VAL-02 | Validation | LOW | NOT FIXED |
| BUG-VAL-03 | Validation | LOW | NOT FIXED |
| BUG-VAL-04 | Validation | LOW | NOT FIXED |

**Fixed this session: 12 bugs** (1 CRITICAL, 7 HIGH, 3 MEDIUM, 1 other)  
**Remaining: 20 bugs** (5 CRITICAL, 4 HIGH, 7 MEDIUM, 4 LOW)

---

## Files Changed in This Session

| File | Change |
|------|--------|
| `backend/app/services/auth_service.py` | Import `hmac`; use `hmac.compare_digest` in `_verify_password` |
| `backend/app/schemas/auth.py` | Added `@field_validator` for email format, password min-length, non-empty required fields |
| `backend/app/api/endpoints/auth.py` | Candidate signup: email/name/password/experience_years inline validation; 5 MB CV cap |
| `backend/app/schemas/jobs.py` | `job_type` → `Literal[...]`; `@field_validator` for non-empty required fields |
| `backend/app/services/job_service.py` | `list_jobs` query: filter out expired jobs via `expires_at > GETDATE()` |
| `backend/app/services/application_service.py` | Validate candidate profile exists; validate job is active before INSERT |
| `backend/app/api/endpoints/applications.py` | Catch `ValueError` → HTTP 400 instead of 500 |
| `backend/app/services/interview_service.py` | Guard `score_interview_answers` against re-scoring a Completed interview |
| `frontend/src/pages/InterviewRoom.tsx` | `API_BASE` reads `VITE_API_URL` env var |
| `frontend/src/pages/InterviewStages.tsx` | `API_BASE` reads `VITE_API_URL` env var; status comparison `'Completed'` (capital C) |

---

## Top Priorities to Address Next

1. **BUG-AUTH-09 / BUG-INT-02 / BUG-APPLY-04 / BUG-JOB-05** — Implement JWT
   authentication. All four CRITICAL unresolved bugs are downstream of this single
   missing capability. Issue a signed JWT on signin; add a `get_current_user` FastAPI
   dependency; thread ownership checks through every protected endpoint.

2. **BUG-JOB-06** — Create `InterviewRounds` (at minimum one) when a job is posted.
   Without this the entire interview pipeline is broken for newly posted jobs.

3. **BUG-VAL-01** — Add protected route wrapper in `App.tsx` that redirects to `/auth`
   when no session token is present.

4. **BUG-AUTH-07** — Store `candidateId` in `sessionStorage` immediately on candidate
   signin (mirror the recruiter pattern).

5. **BUG-AUTH-08** — Add a sign-out button to clear `sessionStorage` and redirect to
   `/auth`.

---

---

# Feature QA Audit — Round 2

**Date:** 2026-06-18  
**Scope:** Job Filtering (`/jobs`) + ATS Scanner (`JobApplyDialog` eligibility check).  
Static code audit; no live server or database required.

---

## 8. Job Filtering Feature

### BUG-FILTER-01 — LIKE Wildcard Injection via location / salary_range Inputs
**Severity:** HIGH | **Status:** FIXED  
**File:** `backend/app/services/job_service.py`

`%` and `_` characters in user-provided `location` or `salary_range` values were passed
directly into LIKE patterns:

```python
# Before
params.append(f"%{location}%")          # user "%" → LIKE '%%%' = match everything
params.append(f"%{salary_range}%")      # user "_" → LIKE '%_%'  = match any single char
```

This is **not** a SQL-injection risk (values are still parameterised), but it completely
breaks filter semantics: a user typing `%` would bypass all location filtering and see
every job.

Fix: added `_escape_like()` that replaces `[` → `[[]`, `%` → `[%]`, `_` → `[_]`, and
updated both LIKE conditions to use `ESCAPE '\\'`:

```python
def _escape_like(value: str) -> str:
    return value.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")

conditions.append("jp.location LIKE ? ESCAPE '\\'")
params.append(f"%{_escape_like(location)}%")
```

---

### BUG-FILTER-02 — Whitespace-Only Text Filter Treated as Active Filter
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `backend/app/services/job_service.py`

A `location` or `salary_range` value of `"   "` (spaces only) passed the `if location:`
truthy check, appending `jp.location LIKE '%   %'` to the WHERE clause. In SQL Server this
would match only jobs whose location literally contains spaces — which is most of them —
producing unexpected results.

Fix: added stripping before the condition check:

```python
location = (location or "").strip() or None
salary_range = (salary_range or "").strip() or None
```

---

### BUG-FILTER-03 — `job_type` Query Param Not Validated Against Allowed Values
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `backend/app/api/endpoints/jobs.py`

`GET /api/jobs?job_type=xyz` silently returned 0 results instead of a 422 validation
error. An API consumer had no way to distinguish "no matching jobs" from "your filter
value is invalid."

Fix: added an explicit guard using the already-defined `VALID_JOB_TYPES` tuple imported
from `schemas/jobs.py`:

```python
if job_type and job_type not in VALID_JOB_TYPES:
    raise HTTPException(
        status_code=422,
        detail=f"job_type must be one of: {', '.join(VALID_JOB_TYPES)}",
    )
```

Also added `ge=1` to the `job_role_id` Query parameter so negative IDs are rejected by
FastAPI before reaching the service.

---

### BUG-FILTER-04 — No Debounce on Text Filter Inputs
**Severity:** HIGH | **Status:** FIXED  
**File:** `frontend/src/pages/Jobs.tsx`

Each character typed in the Location or Salary inputs immediately updated `filters` state,
which triggered the `useEffect([filters])`, which fired a `GET /api/jobs` request. Typing
`"London"` generated 6 sequential HTTP requests.

Fix: separated controlled input state (`locationInput`, `salaryInput`) from filter state.
Text input changes update the input state instantly (so typing feels immediate), but a
`setTimeout(doFetch, 350)` ref debounces the API call. Dropdown filter changes (Role,
Job Type) still fire instantly (0ms delay) since they're discrete selections.

---

### BUG-FILTER-05 — Concurrent Filter Requests Cause Race Condition (Stale Results)
**Severity:** HIGH | **Status:** FIXED  
**File:** `frontend/src/pages/Jobs.tsx`

When filters changed quickly (e.g., clear one, then immediately change another), multiple
`GET /api/jobs` requests were in-flight simultaneously. Whichever completed last would win
and set the `jobs` state, even if it corresponded to an older filter selection. The
rendered list could show results that didn't match the currently-displayed filters.

Fix: added `AbortController` ref (`abortCtrl`). On each filter change, the previous
in-flight request is aborted before the new one is started. `AbortError`s are silently
swallowed in the catch handler.

---

### BUG-FILTER-06 — Stale Error State Persists After Successful Filter Re-Fetch
**Severity:** MEDIUM | **Status:** FIXED  
**File:** `frontend/src/pages/Jobs.tsx`

If a filter request failed (e.g., network blip), `error` was set. A subsequent filter
change that succeeded called `setJobs(data)` but never cleared `error`. Because the render
checks `error` before `jobs.length`, the error message was displayed over a fully-loaded
list.

Fix: added `setError(null)` at the start of `doFetch()` before every re-fetch call.

---

### BUG-FILTER-07 — "No Jobs Match" Shown Prematurely During In-Flight Filter Request
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `frontend/src/pages/Jobs.tsx`

If the previous filter result was zero jobs and a new filter is applied, `jobs.length === 0`
remains true while the new request is in-flight, so the "No jobs match" message is shown
even though results may be about to arrive. Mitigated somewhat by the dim overlay, but
the message text is misleading.

Recommendation: render a neutral "Searching…" message when `filtering === true &&
jobs.length === 0` instead of the "No jobs match" text.

---

### BUG-FILTER-08 — Pagination Supported on Backend but Not Surfaced in UI
**Severity:** LOW | **Status:** NOT FIXED  
**Files:** `backend/app/api/endpoints/jobs.py`, `frontend/src/pages/Jobs.tsx`

The backend correctly implements `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` via `offset` and
`limit` query parameters. The frontend always fetches with the defaults (`limit=50`,
`offset=0`), so users with more than 50 active jobs will never see the full listing.

Recommendation: add a "Load more" button or infinite-scroll that increments `offset` by
`limit` on each activation, appending to the existing `jobs` list.

---

### BUG-FILTER-09 — experience_level_id Filter Not Implementable Without Schema Change
**Severity:** LOW | **Status:** NOT FIXED (architecture)  
**File:** N/A

The original feature spec listed `experience_level_id` as a filter dimension. The
`JobPostings` table has no `experience_level_id` column; `ExperienceLevels` only links to
`CandidateProfiles` and `Questions`. Filtering jobs by experience level would require either:

- Adding an `experience_level_id` FK column to `JobPostings`, or
- A multi-hop join through `Questions` (which is semantically wrong — question difficulty
  ≠ job seniority requirement).

This filter was omitted from the implementation. Add the column to `JobPostings` and
re-run migration to enable it.

---

## 9. ATS Scanner Feature

### BUG-ATS-01 — No Timeout on ATS Check Fetch (User Stuck Indefinitely)
**Severity:** HIGH | **Status:** FIXED  
**File:** `frontend/src/api/applications.ts`

`checkAtsEligibility()` called `fetch()` with no signal. If the LLM endpoint was slow or
unresponsive, the user would see "Checking eligibility…" forever with no way to dismiss
(the button was disabled).

Fix: added a 15-second `AbortController` timeout. On abort, the function falls back to
`{ eligible: true, reason: "Eligibility check timed out; proceeding." }` so the soft gate
never permanently blocks the user:

```typescript
const ctrl = new AbortController()
const timer = setTimeout(() => ctrl.abort(), 15_000)
try {
  const res = await fetch(url, { signal: ctrl.signal })
  ...
} catch (err) {
  if (err instanceof DOMException && err.name === 'AbortError') {
    return { eligible: true, reason: 'Eligibility check timed out; proceeding.' }
  }
  throw err
} finally {
  clearTimeout(timer)
}
```

---

### BUG-ATS-02 — Application Submitted Without User Intent After Dialog Close
**Severity:** CRITICAL | **Status:** FIXED  
**File:** `frontend/src/components/JobApplyDialog.tsx`

Reproduction steps:
1. Open dialog → click "Apply to Job" → ATS check starts (async).
2. While ATS check is in-flight, click ✕ to close the dialog.
3. ATS check completes with `eligible: true`.
4. `handleApplyClick()` resumes execution past the `await checkAtsEligibility(...)` call
   and immediately invokes `submitApplication()` — submitting an application the user
   never confirmed.

Root cause: no guard between the async ATS check completing and the subsequent
`submitApplication()` call.

Fix: added an `isCancelled` ref that is set to `true` in `handleClose()` and checked at
every continuation point in both `handleApplyClick()` and `submitApplication()`:

```typescript
const isCancelled = useRef(false)

function handleClose() {
  isCancelled.current = true   // ← kills any in-flight flow
  resetState()
  onClose()
}

// In handleApplyClick:
const ats = await checkAtsEligibility(job.id, candidateId)
if (isCancelled.current) return          // ← check after every await
```

---

### BUG-ATS-03 — Redundant JSON Format Instructions in System Prompt
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `backend/app/ai/ai_services/ats_service.py:12-23`

`_SYSTEM_PROMPT` instructs the LLM to output raw JSON. However, `with_structured_output(ATSCheckResult)`
already uses OpenAI function-calling to enforce the schema — the system prompt's JSON
instructions are overridden and have no effect. They add noise to the context window and
could cause confusion if the model used does not support function calling.

Recommendation: remove the JSON format block from `_SYSTEM_PROMPT` and keep only the
evaluation guidance (leniency rules, character limit).

---

### BUG-ATS-04 — `reason` Field Has No Maximum Length Enforcement
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `backend/app/ai/ai_services/ats_service.py`

The system prompt asks for a reason "under 150 characters" but LLMs occasionally produce
longer outputs. `ATSCheckResult.reason: str` has no `max_length` constraint and the
`ATSCheckResponse` schema echoes it verbatim. A very long reason string would overflow
the warning box in the UI.

Fix:
```python
from pydantic import Field

class ATSCheckResult(BaseModel):
    eligible: bool
    reason: str = Field(..., max_length=250)
```

And truncate defensively in the frontend:
```typescript
ats.reason.slice(0, 250)
```

---

### BUG-ATS-05 — ATS Endpoint Publicly Accessible (No Auth)
**Severity:** MEDIUM | **Status:** NOT FIXED (depends on BUG-AUTH-09)  
**File:** `backend/app/api/endpoints/applications.py`

`GET /api/applications/ats-check?job_posting_id=X&candidate_id=Y` requires no
authentication. An anonymous caller can probe the eligibility of any candidate for any
job, leaking:
- Whether a CandidateProfile with that ID exists.
- An indirect signal about the candidate's skill set (via the LLM's reason string).

This is consistent with the rest of the unauthenticated API (BUG-AUTH-09) but is worth
calling out specifically because the ATS reason string reveals candidate profile data
indirectly.

---

### BUG-ATS-06 — ATS Endpoint Does Not Verify caller is a Candidate
**Severity:** MEDIUM | **Status:** NOT FIXED  
**File:** `backend/app/api/endpoints/applications.py`

The `/ats-check` endpoint accepts any `candidate_id` string. There is no check that
the ID belongs to a `CandidateProfiles` row vs. a `RecruiterProfiles` row. If a recruiter
ID is passed:
- The `CandidateProfiles` query returns nothing.
- The function returns `eligible=True, reason="Candidate profile not found; proceeding."`.
- The subsequent `POST /apply` call will fail with 400 ("Invalid candidate profile").

The downstream apply endpoint is correctly protected, so this cannot produce a duplicate
or invalid application. However, the ATS check silently "passes" for invalid IDs — this
could mask misuse.

Recommendation: add a `CandidateProfiles` existence check that returns HTTP 400 rather
than a silent pass-through, once JWT auth makes the caller identity verifiable.

---

### BUG-ATS-07 — Double-Click on "Apply Anyway" Can Race the State Update
**Severity:** LOW | **Status:** NOT FIXED  
**File:** `frontend/src/components/JobApplyDialog.tsx`

In the `ats-warning` phase, `isLoading` is `false`, so "Apply Anyway" is enabled. Two
rapid clicks before React re-renders with `phase='applying'` can dispatch two simultaneous
`POST /api/applications/apply` requests. The backend handles this idempotently (returns
the existing `application_id` if an application already exists), so no duplicate row is
created. However, the navigation to `/interview-stages/...` may fire twice.

Recommendation: use a `submitting` ref (not state) toggled synchronously at the top of
`submitApplication()` to guard against re-entry:

```typescript
const submittingRef = useRef(false)

async function submitApplication() {
  if (submittingRef.current) return
  submittingRef.current = true
  ...
  submittingRef.current = false  // reset on error path
}
```

---

## 10. General Validation Checks

### Users → Applications → Interviews Flow: VERIFIED UNCHANGED

The `apply_to_job()` and `get_interview_stages()` service functions are unmodified. The
ATS check is a read-only `GET` endpoint that does not touch the `Applications` or
`Interviews` tables. The `/ats-check` route is declared **before** the parameterised
`/{application_id}/interview-stages` route, preventing any routing conflict.

---

### Recruiter Cannot Trigger ATS + Apply Flow: PARTIALLY PROTECTED

| Layer | Result |
|-------|--------|
| ATS check with recruiter's own ID | Returns `eligible=True` (silently falls through "profile not found" path) |
| ATS check with a candidate's ID (recruiter has it) | Works as intended for that candidate — auth gap |
| `POST /apply` with recruiter's own ID | **Rejected with HTTP 400** — `apply_to_job` validates `CandidateProfiles` exists ✓ |

The backend apply gate is intact. The ATS check is not a security boundary — it is only a
UX hint.

---

### Unsigned Users See All Jobs: VERIFIED CORRECT

`GET /api/jobs` (with or without filters) requires no authentication. The query filters
only on `status = 'active'` and `expires_at > GETDATE()`, not on any user context. ✓

---

### Combined Filters: VERIFIED CORRECT

The WHERE clause builder appends conditions with `AND`, so combining `job_role_id=2` and
`job_type=Remote` produces:

```sql
WHERE jp.status = 'active'
  AND (jp.expires_at IS NULL OR jp.expires_at > GETDATE())
  AND jp.job_role_id = ?
  AND jp.job_type = ?
```

All conditions are parameterised; no hand-crafted SQL fragments exist in the filter path. ✓

---

### Zero Results After Filtering: VERIFIED CORRECT

Backend returns an empty array `[]`; frontend shows "No jobs match your filters.
Try adjusting or clearing them." with a "Clear filters" button. ✓

---

### ATS Fallback on LLM Failure: VERIFIED CORRECT

All three failure modes fall back to `eligible=True`:
1. DB query failure → caught in `try/finally`; candidate/job not found returns `eligible=True` directly.
2. LLM call exception → `except Exception` catches and returns `eligible=True`.
3. Frontend fetch timeout (15s) → `AbortError` handler returns `{ eligible: true, ... }`.
4. Frontend fetch non-timeout error → `catch {}` in `handleApplyClick()` swallows and proceeds to `submitApplication()`.

No path through the ATS check can permanently block an application. ✓

---

## Updated Summary Table (Feature Audit Round 2)

| ID | Area | Severity | Status |
|----|------|----------|--------|
| BUG-FILTER-01 | Filtering | HIGH | **FIXED** |
| BUG-FILTER-02 | Filtering | MEDIUM | **FIXED** |
| BUG-FILTER-03 | Filtering | MEDIUM | **FIXED** |
| BUG-FILTER-04 | Filtering | HIGH | **FIXED** |
| BUG-FILTER-05 | Filtering | HIGH | **FIXED** |
| BUG-FILTER-06 | Filtering | MEDIUM | **FIXED** |
| BUG-FILTER-07 | Filtering | LOW | NOT FIXED |
| BUG-FILTER-08 | Filtering | LOW | NOT FIXED |
| BUG-FILTER-09 | Filtering | LOW | NOT FIXED (schema) |
| BUG-ATS-01 | ATS | HIGH | **FIXED** |
| BUG-ATS-02 | ATS | CRITICAL | **FIXED** |
| BUG-ATS-03 | ATS | LOW | NOT FIXED |
| BUG-ATS-04 | ATS | LOW | NOT FIXED |
| BUG-ATS-05 | ATS | MEDIUM | NOT FIXED (auth) |
| BUG-ATS-06 | ATS | MEDIUM | NOT FIXED (auth) |
| BUG-ATS-07 | ATS | LOW | NOT FIXED |

**Fixed this round: 7 bugs** (1 CRITICAL, 3 HIGH, 3 MEDIUM)  
**Remaining this round: 9 bugs** (0 CRITICAL, 0 HIGH, 2 MEDIUM, 7 LOW/arch)

---

## Files Changed in This Session (Round 2)

| File | Change |
|------|--------|
| `backend/app/services/job_service.py` | Added `_escape_like()`; strip whitespace from text filters; use `ESCAPE '\\'` on LIKE clauses |
| `backend/app/schemas/jobs.py` | Added `job_role_id: int` to `JobListItem` |
| `backend/app/api/endpoints/jobs.py` | Added `job_type` validation against `VALID_JOB_TYPES`; added `ge=1` to `job_role_id` |
| `backend/app/ai/ai_services/ats_service.py` | New file: LLM-based ATS eligibility service |
| `backend/app/schemas/applications.py` | Added `ATSCheckResponse` |
| `backend/app/api/endpoints/applications.py` | Added `GET /ats-check` endpoint (declared before `/{application_id}` to prevent routing conflict) |
| `frontend/src/api/jobs.ts` | Added `JobFilters` interface; `fetchJobs()` accepts filters + optional `AbortSignal` |
| `frontend/src/api/applications.ts` | New file: `checkAtsEligibility()` with 15-second abort timeout |
| `frontend/src/pages/Jobs.tsx` | Filter panel with debounced text inputs, AbortController, clear error on re-fetch |
| `frontend/src/css/Jobs.css` | Filter panel styles |
| `frontend/src/components/JobApplyDialog.tsx` | ATS check flow: `isCancelled` ref, phase state machine, warning banner, "Apply Anyway" |
| `frontend/src/css/JobApplyDialog.css` | ATS warning banner + actions styles |
