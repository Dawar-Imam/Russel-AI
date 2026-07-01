# System Logic — Test Report (v2)

**Companion to:** `system_logic_test_cases.md`
**Method:** Static code audit (Grep/Read across `backend/app/`) plus a full route
inventory (`grep -n "@router\." backend/app/api/endpoints/*.py`) and a full auth-mechanism
search (`grep -rn "Depends|JWT|Authorization|session_token" backend/app/`). No live
server/DB was running during this pass. Each finding includes **Input payload**,
**API/module involved**, **Expected vs. Actual**, **Severity**, **Suggested fix
(architectural-level preferred)**.

---

## Read This First: One Root Cause Behind Most Findings Below

A complete grep of `backend/app/api/` and `backend/app/services/auth_service.py` for
`Depends`, `JWT`, `Authorization`, `access_token`, `session_token` returned **zero
matches**. There is no server-side session/auth-verification mechanism anywhere in this
backend. Every endpoint that takes a `candidate_id`/`recruiter_id` parameter trusts it
at face value from the request — there is no code path anywhere that checks "is the
caller actually who they claim to be."

This single fact is the root cause of every IDOR finding in this report (F-SL-01 through
F-SL-05 below). They are listed individually because each has a distinct exploitable
endpoint and a distinct blast radius, but **fixing them one at a time without addressing
the root cause will not close the class of bug** — any new endpoint added in the future
that takes an ID parameter will reintroduce the same vulnerability unless the
architectural fix (below) is in place first. F-SL-06 through F-SL-09 are separate,
unrelated findings (a missing business-rule check and two concurrency gaps).

---

## Severity Summary

| Severity | Confirmed | Not Yet Executed |
|---|---|---|
| CRITICAL | 6 | 6 |
| HIGH | 3 | 14 |
| MEDIUM | 0 | 8 |
| LOW | 0 | 3 |

---

## CONFIRMED Findings

### F-SL-01 (SL-28) — Recruiter analytics endpoints: full cross-recruiter data exposure
**Severity:** CRITICAL

**Input payload:** `GET /jobs/{job_id}/stats`, `GET /jobs/{job_id}/rounds/{round_order}/candidates`, `GET /jobs/{job_id}/candidate-panel/{application_id}?interview_id=`, `GET /jobs/interview-qa/{interview_id}` — any `job_id`/`application_id`/`interview_id` not belonging to the caller.

**API / module involved:** `backend/app/api/endpoints/jobs.py:107-143`; `backend/app/services/job_service.py:248,340,374,497`.

**Expected vs. Actual:**
- Expected: 403/404 unless the caller is the owning recruiter.
- Actual: 200 with full candidate PII, scores, interview transcripts, and feedback for any job — recruiter identity isn't even a parameter on these routes.

**Suggested fix (architectural):** See the root-cause fix below — this resolves automatically once real session auth exists and these routes derive the caller's `recruiter_id` server-side instead of accepting it implicitly via no check at all.

---

### F-SL-02 (SL-29) — Candidate interview endpoints: cross-candidate read AND write access
**Severity:** CRITICAL

**Input payload:** `GET /applications/{application_id}/interview-stages`, `GET /applications/{application_id}/interviews/{interview_id}/questions`, `POST /interviews/{interview_id}/generate-questions`, `POST /interviews/{interview_id}/score-answers` — any `application_id`/`interview_id` not belonging to the caller.

**API / module involved:** `backend/app/api/endpoints/applications.py:82-99`; `backend/app/services/application_service.py:115,317`; `backend/app/services/interview_service.py:266,538,651`, especially `_save_candidate_answers` (`interview_service.py:168`).

**Expected vs. Actual:**
- Expected: 403/404 on read; write rejected entirely for non-owners.
- Actual: full read access to another candidate's questions/feedback/scores; **write access** — `score-answers` accepts caller-supplied `answers` and persists them against any `interview_id`, with zero ownership check. A malicious candidate can overwrite another candidate's real answers before they submit, or after, corrupting their actual outcome.

**Suggested fix (architectural):** Same as F-SL-01 — root-cause fix, applied to candidate-scoped routes specifically requiring a `candidate_id == Applications.candidate_id` (resolved server-side from session) check before any read or write.

---

### F-SL-03 (SL-30) — `/jobs/mine` hands over a recruiter's entire job list to anyone who swaps the parameter
**Severity:** CRITICAL

**Input payload:** `GET /jobs/mine?recruiter_id={any_recruiter_id}`.

**API / module involved:** `backend/app/api/endpoints/jobs.py:50-56`; `backend/app/services/job_service.py:230` (`list_recruiter_jobs`).

**Expected vs. Actual:**
- Expected: only returns jobs for the authenticated caller.
- Actual: returns whatever `recruiter_id`'s job list is requested. This is functionally worse than F-SL-01 in terms of attack economics — it's not just "exploit if you already know a target job_id," it **hands over the full list of job_ids to attack next**, collapsing the "find a target" step of F-SL-01 into zero effort.

**Suggested fix (architectural):** Same root-cause fix. Flagged separately because this is the highest-leverage single endpoint to fix first if a full session-auth rollout must be staged incrementally — closing this one endpoint significantly raises the cost of discovering targets for F-SL-01, even before the rest of the rollout completes.

---

### F-SL-04 (SL-21) — Score tampering is a direct, working primitive, not just data exposure
**Severity:** CRITICAL

**Input payload:** `POST /interviews/{victim_interview_id}/score-answers` with `fetch_from_db=False` and a hand-crafted `answers` array of the attacker's choosing.

**API / module involved:** `backend/app/api/endpoints/interviews.py:43-60`; `backend/app/services/interview_service.py:651` (`score_interview_answers`) → `_save_candidate_answers` (line 168) → `_save_scores_and_complete` (line 230, including the `_mark_subsequent_rounds_not_needed`/`_maybe_mark_hired` cascades added this engagement).

**Expected vs. Actual:**
- Expected: rejected — only the owning candidate (server-verified) can submit answers for their own interview.
- Actual: succeeds fully. This is the most severe single finding in the whole audit because it's not passive data exposure — it's an active sabotage primitive that also **triggers real downstream state changes** (the `Not Needed`/`HIRED` cascades built this engagement), meaning a successful attack doesn't just corrupt one row, it can cascade into wrongly failing a victim out of their entire remaining interview pipeline.

**Suggested fix (architectural):** Same root-cause fix, with this endpoint as the top rollout priority given the active-sabotage blast radius.

---

### F-SL-05 (SL-10) — Job-posting attribution is fully spoofable
**Severity:** CRITICAL

**Input payload:** `POST /jobs` with `recruiter_id` set to any value other than the caller's own (no session to contradict it).

**API / module involved:** `backend/app/api/endpoints/jobs.py:87-97`; `backend/app/schemas/jobs.py` (`JobPostRequest.recruiter_id`).

**Expected vs. Actual:**
- Expected: `recruiter_id` derived server-side from an authenticated session, request-body value ignored or used only for cross-validation.
- Actual: trusted as-is. A job can be created and attributed to a recruiter who never created it.

**Suggested fix (architectural):** Same root-cause fix. Lower exploitation incentive than F-SL-01–04 (less obviously valuable to an attacker — "create a job under someone else's name" is more of a nuisance/confusion vector than a data-theft one) but included in the CRITICAL tier because it's the same missing control and the same one-line fix once session auth exists.

---

### F-SL-06 (SL-18) — Round 1 startable without ATS having passed at all
**Severity:** CRITICAL

**Input payload:** `POST /interviews/{first_round_interview_id}/generate-questions` for an application whose `Applications.status` is `ATS_PENDING` or `ATS_FAIL`.

**API / module involved:** `backend/app/services/interview_service.py:538` (`generate_interview_questions`) — its only completion-state guard checks the `Interviews.status` column, never the parent `Applications.status`/ATS outcome. `backend/app/services/application_service.py:13-112` (`apply_to_job`) pre-creates every round's `Interviews` row as `Scheduled` at apply time, **before ATS has even run**.

**Expected vs. Actual:**
- Expected: an interview round cannot be started for an application that hasn't passed ATS, server-side, regardless of request origin.
- Actual: nothing stops it via direct API call — the frontend's gating (only showing the "go to interview" CTA after ATS passes) is the only control, and per the root-cause note, frontend gating is advisory only.

**Suggested fix (architectural):** This one is independent of the session-auth root cause — it's a missing business-rule check, not an authorization gap (the candidate calling this *is* themselves; the problem is the rule itself isn't enforced). Add an explicit `Applications.status == 'ATS_PASS'` (or `IN_PROGRESS`/`HIRED`, per `_ATS_PASSED_STATUSES`) check inside `generate_interview_questions` before allowing question generation, sourced from a join back to the parent `Applications` row via the interview's `application_id` — the data needed is already one join away (`get_interview_context` already performs this exact join for other purposes, at `interview_service.py:37-72`, so the data-access pattern to extend already exists in the codebase).

---

### F-SL-07 (SL-12) — Concurrent apply requests produce duplicate Applications/Interviews rows
**Severity:** HIGH

**Input payload:** Two near-simultaneous `POST /applications/apply` for the same `candidate_id` + `job_posting_id` (double-click, retried request, or two tabs).

**API / module involved:** `backend/app/services/application_service.py:47-75` (check-then-insert on `Applications`), repeated at `:89-105` for per-round `Interviews` rows.

**Expected vs. Actual:**
- Expected: exactly one `Applications` row and one set of per-round `Interviews` rows per candidate+job pair, regardless of request timing.
- Actual: no unique constraint or transaction isolation guards the check-then-insert sequence — two concurrent requests can both pass the "not found" check before either commits, producing duplicates that double-count in `get_job_stats`'s `total_applicants`/`hired_count` and create the two-independent-state-machines failure mode detailed in `SL-SB-02`.

**Suggested fix (architectural):** Add a DB-level unique constraint on `Applications(job_id, candidate_id)` — this converts the race from "silent duplication" into "clean constraint-violation error," which the service layer can catch and respond to idempotently (return the existing application). This is a more robust fix than application-level locking because it holds regardless of how many app instances/processes are running concurrently, which a Python-level lock would not.

---

### F-SL-08 (SL-21 / AI-SB-02 cross-reference) — TOCTOU gap in score-answers persistence
**Severity:** HIGH

**Input payload:** Two near-simultaneous `POST /interviews/{id}/score-answers` for the same `interview_id`.

**API / module involved:** `backend/app/services/interview_service.py:651-758` (`score_interview_answers`) — status-check connection closes before the LLM call; a second connection persists results afterward, with no re-check inside the same transaction as the final write.

**Expected vs. Actual:**
- Expected: exactly one scoring result persisted per interview.
- Actual: two concurrent requests can both pass the "not yet completed" check (read on separate connections, separated by a multi-second LLM-call window) and both reach `_save_scores_and_complete`, with the second write silently overwriting the first — no optimistic-locking/version check on the final `UPDATE Interviews` statement.

**Suggested fix (architectural):** Re-check status inside the same transaction as the final write — add `AND status NOT IN ('Pass','Failed','Not Needed')` directly to the final `UPDATE Interviews` statement so a second concurrent write affects 0 rows (a no-op) instead of silently overwriting. This is a small, surgical fix (one SQL clause) that closes the gap without restructuring the existing two-connection design (which is intentionally structured that way to avoid holding a DB connection during the slow LLM call — a reasonable design choice that just needs its endpoint hardened, not reversed).

---

### F-SL-09 (SL-SB-01 architectural restatement) — No transaction atomicity guarantee beyond clean-exception rollback
**Severity:** HIGH

**Input payload:** A process-level failure (OOM kill, host restart, connection drop) during any multi-row write sequence — `apply_to_job`'s Applications+Interviews creation, `post_job`'s JobPostings+JobRequiredSkills+InterviewRounds creation, `_store_generated_questions`'s per-question insert loop.

**API / module involved:** All of the above; no explicit `BEGIN TRANSACTION`/`SAVEPOINT` usage found anywhere in the codebase — atomicity currently relies entirely on pyodbc's implicit commit/rollback-on-close behavior.

**Expected vs. Actual:**
- Expected: all-or-nothing writes regardless of failure mode (clean exception or process death).
- Actual: confirmed safe against clean Python-level exceptions (rollback-on-close); **not verified** against a connection killed mid-write by external process failure, which depends on SQL Server's own connection-loss transaction handling — untested in this codebase.

**Suggested fix (architectural):** Make transaction boundaries explicit (`BEGIN`/`COMMIT`/`ROLLBACK`) rather than relying on driver-default implicit behavior, and add integration tests that simulate a mid-write connection kill (not just a Python exception) for the three write sequences named above, at minimum for `apply_to_job` since it's the highest-traffic multi-row write in the system.

---

## The Architectural Fix (Applies to F-SL-01 through F-SL-05)

Introduce real session-based authentication:
1. **Issue a signed token at signin** (JWT is the standard choice; the project has no auth-library dependency currently, so this is a new addition, not a refactor of existing infra) containing `user_id` and `userType` (`candidate`/`recruiter`), with a reasonable expiry.
2. **Add a FastAPI dependency** (`Depends(get_current_candidate)` / `Depends(get_current_recruiter)`) that validates the token from an `Authorization` header and returns the verified identity — applied to every endpoint currently accepting `candidate_id`/`recruiter_id` as a plain parameter.
3. **Stop accepting `candidate_id`/`recruiter_id` as client-trusted request parameters** on any endpoint performing a sensitive read or any write — derive them exclusively from the verified token. Endpoints that currently take these as path/query/body params need that param removed (or kept only for routes genuinely needing to look up a *different* user's public data, with an explicit ownership check against the new verified identity for anything private).
4. **Frontend**: store the token (not just raw IDs) in `sessionStorage`/memory, attach it as an `Authorization: Bearer` header on every request, remove reliance on client-asserted IDs for anything the backend should be independently verifying.

This is a genuinely significant scope of work (touches every endpoint), which is exactly
why it's worth doing once, correctly, rather than patching each of F-SL-01–05
individually with ad hoc per-endpoint `WHERE recruiter_id = ?` filters that still trust
a client-supplied `recruiter_id` to filter *by* (a filter using an unverified value is
not a real fix — it just changes "see everyone's data" to "see whatever data you claim
to be entitled to," which is barely better). If a full rollout genuinely cannot happen
before a near-term deployment, the *minimum* viable interim mitigation is documented per
finding above, but should be treated as a stopgap, not a resolution.

---

## NOT YET EXECUTED — Requires Live Environment

| ID | Severity | What to run |
|---|---|---|
| SL-01–SL-05 | high/critical/medium/critical/low | Auth edge cases: same-email-both-roles, brute-force/lockout, email normalization, SQLi spot-check on auth fields specifically, oversized company_name |
| SL-06–SL-09, SL-11 | medium/high/medium/high/low | Past-expiry job creation; non-sequential round_order live behavior; failing_criteria direct-API boundary; zero-round job hire-path verification (cross-ref `ai_test_report.md` F-AI finding); duplicate job postings dashboard rendering |
| SL-12, SL-13 | high, high | Concurrent double-apply load test; CV-swap-after-ATS-fail re-evaluation behavior — **SL-13 needs clarification of intended product behavior before it can even be scored pass/fail**, since it's ambiguous whether re-evaluation-on-CV-update is a wanted feature or an unwanted gaming vector |
| SL-14–SL-17 | medium/high/medium/medium | Expiry boundary; stale-page apply; forged candidate_id; non-active-job direct apply |
| SL-19 | high | Mid-transaction failure injection during apply_to_job's multi-row write — confirm atomicity holds under real connection-loss, not just clean exceptions |
| SL-20 | medium | Genuinely concurrent multi-interview sessions, same human, two jobs |
| SL-22 | critical (resolved via SL-21's existing path) | Confirm no *additional* direct-to-HIRED route exists beyond the score-tampering path already confirmed |
| SL-23, SL-24 | high, high | Re-run existing `test_round_cascade.py`-covered scenarios end-to-end through real API calls (regression confirmation, not new discovery) |
| SL-25 | medium | Round deactivation mid-pipeline — verify both forward (`_maybe_mark_hired` re-scoping) and backward (already-completed-round visibility) behavior |
| SL-26, SL-27 | high, low | Validator never-returns-Pass-on-forced-fail confirmation; cross-job HIRED isolation regression check |
| SL-31 | medium | Candidate panel for orphaned profile — clean 404 vs. 500 |
| SL-32–SL-34 | low/medium/medium | Sparse-metadata job feed rendering; duplicate-job-role data governance audit; aggregate count accuracy under the confirmed SL-12 race |

**Priority recommendation:** The architectural fix (session auth) should be treated as a
blocking pre-launch item, not a backlog item — it resolves F-SL-01 through F-SL-05 in one
piece of work rather than five. After that, SL-06 (zero-round hire path) and SL-13 (CV
re-evaluation ambiguity) are the next highest-value items because they're product-logic
gaps, not security gaps, and need a product decision before an engineering fix can even
be correctly scoped.
