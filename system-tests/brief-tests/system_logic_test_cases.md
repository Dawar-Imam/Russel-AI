# System Logic — Brief Test Cases (Critical & High Only)

Scope: full candidate + recruiter journey across `backend/app/services/*.py` and HTTP endpoints.
Root cause: zero server-side session enforcement anywhere in the backend — every endpoint trusts whatever ID the client sends.
Kept: all critical confirmed gaps, high-severity confirmed bugs. Dropped: low/medium, regression-guards, structurally-safe cases.

---

## SL-02 — Credential brute-force with no lockout
**Category:** abuse | **Severity:** critical
**Scenario:** Script 50+ signin attempts against one email with wrong passwords, no delay.
**Expected:** Rate limiting or progressive lockout after N failures.
**Failure Mode:** No rate-limiting or lockout found anywhere in `auth_service.py`. A successful brute-force grants the same raw ID the client uses everywhere else — with zero further verification.

## SL-04 — SQL injection through auth fields
**Category:** adversarial | **Severity:** critical
**Scenario:** Submit `' OR '1'='1`, `'; DROP TABLE Users; --` in every signup/signin field.
**Expected:** Treated as literal string content; no query structure alteration.
**Failure Mode:** Parameterized `?` queries confirmed generally — this case specifically re-verifies `auth_service.py` wasn't missed. If it was, it is directly exploitable.

## SL-07 — Non-sequential / duplicate `round_order` values
**Category:** edge | **Severity:** high
**Scenario:** POST a job with rounds `[{round_order:1},{round_order:1},{round_order:5}]`.
**Expected:** Rejected or auto-normalized to `[1,2,3]` server-side.
**Failure Mode:** No validation found in `InterviewRoundInput`. Directly breaks `_maybe_mark_hired`'s "no later active round" check and `get_interview_stages`'s `current_round_id` resolution.

## SL-09 — Zero interview rounds — hire path never fires
**Category:** edge | **Severity:** high
**Scenario:** Post a job with `interview_rounds: []`. Candidate applies and passes ATS.
**Expected:** Candidate marked `HIRED` immediately upon ATS pass (per recruiter UI copy).
**Failure Mode:** **Confirmed structural gap**: `_maybe_mark_hired` only fires from round scoring. A zero-round job has no scoring event, so `Applications.status` stays `ATS_PASS` forever.

## SL-10 — Tampered `recruiter_id` in job-post payload
**Category:** adversarial | **Severity:** critical
**Scenario:** Recruiter A edits the `POST /jobs` body to set `recruiter_id` to Recruiter B's ID.
**Expected:** Rejected — `recruiter_id` should be derived from a verified session, never trusted from client body.
**Failure Mode:** **Confirmed exploitable**: `recruiter_id` in `JobPostRequest` is a plain field. A job is created attributed to Recruiter B, who never requested it, with applicants accumulating against their account.

## SL-12 — Concurrent double-apply (race condition)
**Category:** race-condition | **Severity:** high
**Scenario:** Two near-simultaneous `POST /applications/apply` for the same `candidate_id` + `job_posting_id`.
**Expected:** Exactly one `Applications` row, one set of per-round `Interviews` rows.
**Failure Mode:** **Confirmed**: check-then-insert race in `apply_to_job`, no unique constraint. Produces duplicate rows, double-counted in `get_job_stats`, and feeds SL-SB-02.

## SL-18 — ATS eligibility bypassed via direct API call
**Category:** adversarial | **Severity:** critical
**Scenario:** After ATS fails, candidate directly calls `POST /interviews/{first_round_id}/generate-questions`.
**Expected:** Rejected — interview rounds must not be startable on a failed-ATS application.
**Failure Mode:** **Confirmed gap**: `generate_interview_questions` only checks the interview's own `status` (`Scheduled` = startable). All round `Interviews` rows are pre-created as `Scheduled` at apply time, before ATS even runs. Every failed-ATS candidate has fully startable interview rows accessible via direct API.

## SL-21 — Score tampering via direct score-answers call (IDOR + sabotage)
**Category:** adversarial | **Severity:** critical
**Scenario:** Candidate B calls `POST /interviews/{candidate_A_interview_id}/score-answers` with a hand-crafted payload.
**Expected:** Rejected — a candidate can only submit answers for their own interview.
**Failure Mode:** **Confirmed critical IDOR**: zero ownership check. Candidate B can overwrite Candidate A's answers with any text, trigger scoring on that fabricated content, and write the result onto A's `Interviews` row — including triggering `_maybe_mark_hired` / `_mark_subsequent_rounds_not_needed` cascades on behalf of a candidate they are sabotaging.

## SL-28 — Cross-recruiter analytics IDOR
**Category:** adversarial | **Severity:** critical
**Scenario:** Recruiter A calls `GET /jobs/{recruiter_B_job_id}/stats`, `/rounds/{order}/candidates`, `/candidate-panel/{app_id}`, `/jobs/interview-qa/{interview_id}` using Recruiter B's IDs.
**Expected:** 403/404.
**Failure Mode:** **Confirmed**: zero ownership filtering on any of these four endpoints.

## SL-29 — Cross-candidate interview IDOR including write access
**Category:** adversarial | **Severity:** critical
**Scenario:** Candidate B accesses/mutates Candidate A's `interview-stages`, `questions`, and `score-answers` using A's IDs.
**Expected:** 403/404 on read; write blocked entirely.
**Failure Mode:** **Confirmed**: same root cause as SL-28; the write path additionally allows score manipulation (SL-21).

## SL-30 — `/jobs/mine` returns another recruiter's listings
**Category:** adversarial | **Severity:** critical
**Scenario:** `GET /jobs/mine?recruiter_id={other_recruiter_id}`.
**Expected:** Rejected or returns nothing unless the caller is that recruiter.
**Failure Mode:** `list_recruiter_jobs(recruiter_id)` takes the parameter at face value. This is also the discovery step that hands over the target job_ids needed to attack SL-28.

---

## SL-SB-01 — There is no authentication layer; every permission is theater
**Category:** adversarial / system-break | **Severity:** critical
**Scenario:** Call any endpoint with any `candidate_id`/`recruiter_id`/`application_id` — no token, no session, just a known or guessed ID.
**Expected:** A real system distinguishes "I am X, here is proof" from "I am claiming to be X."
**Failure Mode:** Zero-result grep across the entire backend for any session/token/auth-dependency mechanism. SL-10, SL-18, SL-21, SL-28, SL-29, SL-30 are all the same root cause through different endpoints. Fix: introduce JWT issued at signin, validated via a FastAPI dependency, so IDs are derived server-side from a verified token.

## SL-SB-02 — Duplicate application race creates two diverging interview state machines
**Category:** race-condition / system-break | **Severity:** critical
**Scenario:** Trigger SL-12 so two `Applications` rows exist for one candidate-job pair. Candidate proceeds through interviews — each round-completion cascade runs independently and inconsistently across both duplicate sets.
**Expected:** One human, one candidacy, one consistent state per job.
**Failure Mode:** The cascade logic is correct in isolation but assumes `application_id` is unique per human-per-job — the apply race directly violates this. A candidate could fail on one duplicate and still have a fully live, unfailed second duplicate to attempt.
