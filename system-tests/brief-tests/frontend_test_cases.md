# Frontend — Brief Test Cases (Critical & High Only)

Scope: `frontend/src/pages/*.tsx`, `frontend/src/components/*.tsx`.
Kept: confirmed critical/high bugs and the one system-break that frames all others. Dropped: low/medium, regression-guards, "safe by code reading" cases.

---

## FE-02 — Double submission of the same application
**Category:** race-condition | **Severity:** high
**Scenario:** Rapidly double-click "Apply" in `JobApplyDialog.tsx` before first request resolves.
**Expected:** Button disables on first click; server produces one application row.
**Failure Mode:** No confirmed client-side double-submit guard; backend SL-12 race also unguarded — two-layer gap.

## FE-03 — UI shows "Applied" but backend request actually failed
**Category:** adversarial | **Severity:** critical
**Scenario:** Kill the backend immediately after clicking Apply so the request never completes, but any optimistic UI update already fired.
**Expected:** No "Applied" badge or dialog-close-as-success until a genuine 2xx is received.
**Failure Mode:** If `JobApplyDialog`/`Jobs.tsx` set success state before awaiting the response body, a failed request silently drops the candidate from a pipeline they believe they joined.

## FE-12 — Manually tampered session state mid-session
**Category:** adversarial | **Severity:** critical
**Scenario:** Edit `sessionStorage.userType` from `candidate` to `recruiter` (or delete `candidateId`) via devtools while on an authenticated page.
**Expected:** App detects inconsistent state and forces re-auth.
**Failure Mode:** `sessionStorage` is the only identity record — there is no server-side cross-check. Whatever tampered ID the client sends, the server honours.

## FE-16 — File upload above the 5 MB backend cap
**Category:** edge | **Severity:** high
**Scenario:** Select a 6 MB+ file for CV upload.
**Expected:** Client-side rejection before the network request fires, with a clear message.
**Failure Mode:** Slow upload that fails late with a generic 413, no useful feedback to the candidate.

## FE-22 — Fabricated `applicationId` in URL
**Category:** adversarial | **Severity:** high (fake) / critical (real-but-foreign via SL-29)
**Scenario:** Navigate to `/application-progress/00000000-0000-0000-0000-000000000000`.
**Expected:** Clean "not found" state.
**Failure Mode:** A real-but-not-yours `applicationId` does not 404 — it loads someone else's progress (confirmed backend IDOR SL-29).

## FE-25 — Resume in-progress interview vs. restart
**Category:** edge | **Severity:** high
**Scenario:** Enter an interview, browser-back to Application Progress, click in again.
**Expected:** Resumes the same in-progress interview; does not re-trigger question generation on an already-`In Progress` interview.
**Failure Mode:** Double question generation against a live interview round.

## FE-30 — Direct devtools manipulation of the score-answers request
**Category:** adversarial | **Severity:** critical
**Scenario:** From browser console on the Interview Room page, replay the score-answers `fetch()` with a different `interview_id` than the one loaded.
**Expected:** Rejected server-side regardless of what the frontend sends.
**Failure Mode:** Confirmed SL-29/SL-21 IDOR — backend accepts any `interview_id` with zero ownership check.

## FE-31 — Timer hits zero mid-answer
**Category:** edge | **Severity:** high
**Scenario:** Let the countdown reach 0 while an answer is unsubmitted.
**Expected:** Clear auto-submit or "time's up" state — never a silent freeze.
**Failure Mode:** Candidate cannot tell if their answer was captured.

## FE-33 — Round-order recalculation on mid-list removal
**Category:** edge | **Severity:** high
**Scenario:** Build a 10+ round list in the recruiter dashboard, remove a round from the middle.
**Expected:** `round_order` recalculated cleanly (no gaps/duplicates) before submission.
**Failure Mode:** Feeds directly into confirmed-risky SL-07 backend gap.

## FE-36 — Past-date `expires_at` via the date picker
**Category:** abuse | **Severity:** high
**Scenario:** Attempt to select a past date in the job-post form.
**Expected:** Picker blocks past dates or a clear validation error appears.
**Failure Mode:** Frontend is currently the **only** defense (backend SL-06 has no past-date check).

---

## FE-SB-01 — Frontend is the entire security boundary, and it is trivially bypassable
**Category:** adversarial / system-break | **Severity:** critical
**Scenario:** Drive every state transition (apply, score, post job, view analytics) via direct `fetch()` calls — never touch the UI.
**Expected:** Backend independently enforces every business rule the frontend enforces.
**Failure Mode:** It does not, per confirmed IDOR / no-session-layer findings. Every disabled button, hidden CTA, and route guard is a UX courtesy, not a security control.
