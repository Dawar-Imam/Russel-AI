# Frontend — UI, Field Validation & Abuse Test Cases (v2)

Scope: `frontend/src/pages/*.tsx`, `frontend/src/components/*.tsx`, form validation,
layout robustness, client-side state handling. **Manual / exploratory test cases** —
automated e2e (Playwright) is intentionally out of scope per project decision; run these
by hand against a local dev server, or have an agent drive a real browser on request.

**Framing note:** the frontend's validation is, by design and by the confirmed lack of
any backend session layer (see `system_logic_test_cases.md`'s root-cause note), the
*only* line of defense for a large class of these cases — not a UX nicety on top of a
secure backend. Every "form bypass via direct API call" case below is not academic; it
is the literal, currently-available attack path, since nothing server-side stops it
either.

## Required Fields (every case)

Test Case ID · Category (`normal` / `edge` / `abuse` / `adversarial` / `stress` /
`race-condition`) · Input Scenario · Expected Behavior · Failure Mode · Severity
(`low` / `medium` / `high` / `critical`)

---

## 1. Form Bypass via Direct API Calls

### FE-01 — Required fields submitted empty by calling the API directly
**Category:** abuse
**Input Scenario:** Skip the UI entirely; `fetch()` `POST /auth/signup`, `POST /jobs`, `POST /applications/apply` directly from devtools/a script with required fields (`first_name`, `description`, `job_posting_id`, etc.) set to empty string or omitted.
**Expected Behavior:** Backend Pydantic validators independently reject every case the frontend would have blocked — frontend validation is a UX convenience, not the actual gate.
**Failure Mode:** Largely confirmed safe for auth fields (documented `@field_validator` empty-checks exist per the prior session's `TESTING_REPORT.md`). **Not yet confirmed** for every field on every endpoint — `JobPostRequest.expires_at` has no past-date check (SL-06), `round_order` has no sequentiality check (SL-07) — these are exactly the "form bypass" cases where frontend might constrain input (e.g. a date picker disallowing past dates) but the backend doesn't independently enforce the same rule.
**Severity:** high

### FE-02 — Double submission of the same application
**Category:** race-condition
**Input Scenario:** Rapidly double-click "Apply" in `JobApplyDialog.tsx` before the first request resolves, or fire two manual concurrent `fetch()` calls to `/applications/apply`.
**Expected Behavior:** Button disables immediately on first click (client-side mitigation); even if both requests reach the server, the result is one application, not two.
**Failure Mode:** No confirmed client-side double-submit guard in `JobApplyDialog.tsx` (needs live check of whether the submit button has a `disabled` state tied to an in-flight request flag). Backend has the confirmed SL-12 race regardless, so this is a two-layer gap: missing frontend debounce **and** missing backend uniqueness constraint, neither compensating for the other.
**Severity:** high

### FE-03 — UI shows "Applied" but the backend request actually failed
**Category:** adversarial
**Input Scenario:** Throttle/break the network (devtools offline simulation, or kill the backend) immediately after clicking Apply, such that the request never completes but any optimistic UI update already fired.
**Expected Behavior:** UI state strictly reflects confirmed server state — no "Applied" badge, no dialog-close-as-success, until a genuine 2xx response is received.
**Failure Mode:** Needs live verification of whether `JobApplyDialog`/`Jobs.tsx` perform any optimistic UI update before awaiting the actual response. If `created`/success state is set from anything other than the awaited response body, a failed request could leave the candidate believing they applied when they did not — silently dropping them from a job they think they're in the pipeline for, with no error ever shown.
**Severity:** critical

### FE-04 — Invalid data injected directly via form fields, bypassing client constraints
**Category:** abuse
**Input Scenario:** Use devtools to remove a `maxlength`/`type="number"`/`pattern` attribute from an input element, then enter data that violates the removed constraint (e.g. text into a number field, 50,000 characters into a length-capped field), and submit normally through the UI.
**Expected Behavior:** Backend validation catches what the now-removed client constraint would have blocked — this is functionally identical to FE-01 but reachable without ever opening a network tab, via the most casual form of tampering (editing HTML attributes), which lowers the skill bar for triggering it considerably.
**Failure Mode:** Same gaps as FE-01, restated under a lower-effort attack vector worth tracking separately since "right-click → inspect → delete an attribute" is something far more users will stumble into than "open the Network tab and replay a request."
**Severity:** high

### FE-05 — Offline-mode resubmission duplication
**Category:** abuse / edge
**Input Scenario:** Candidate submits the Apply form while genuinely offline (request queued/fails silently per browser/PWA-like behavior, if any exists) or on a flaky connection that times out client-side; candidate, seeing no confirmation, manually retries the exact same submission once connectivity returns — potentially multiple times if each retry also appears to fail/hang.
**Expected Behavior:** Retries of a logically-identical apply request should resolve to the existing application (idempotent), per `apply_to_job`'s documented "already exists → update, don't duplicate" intent — *when the request actually reaches the server*. The danger case is specifically when multiple queued/retried requests all reach the server in a tight window after connectivity returns (effectively a burst of near-simultaneous requests), reintroducing SL-12's race condition through an offline-retry pattern rather than a deliberate double-click.
**Failure Mode:** No offline-queueing/service-worker behavior was found in this codebase (no PWA manifest/service worker detected in `frontend/`), meaning "offline mode" here just means "requests fail with a network error" rather than a sophisticated queue-and-replay system — which is actually the *safer* failure mode (no hidden duplicate-send queue to misfire later), but it does mean the user experience for FE-03 (silent failure with stale optimistic UI) is the realistic risk here, not a sophisticated sync-conflict.
**Severity:** medium

---

## 2. Auth Forms

### FE-06 — Whitespace-only required fields
**Category:** edge
**Input Scenario:** Enter only spaces into `first_name`/`last_name` on signup.
**Expected Behavior:** Client-side validation blocks submit; if bypassed, backend's documented strip-and-check validator catches it.
**Severity:** medium

### FE-07 — Malformed email formats
**Category:** edge
**Input Scenario:** `notanemail`, `a@b`, `test@`, unicode-only strings, emoji as email.
**Expected Behavior:** Inline validation before any network call.
**Severity:** medium

### FE-08 — Password length boundary
**Category:** edge
**Input Scenario:** Exactly 7 vs. exactly 8 characters (the documented backend minimum).
**Expected Behavior:** Frontend's enforced minimum matches the backend's exactly — no gap where the frontend accepts something the backend then rejects with a confusing late error.
**Severity:** medium

### FE-09 — Extremely long input into every signup field
**Category:** stress
**Input Scenario:** Paste 10,000+ characters into name/company/designation fields.
**Expected Behavior:** No layout break; clean client-side cap or clean backend rejection — not a silently-truncated submission the user never knows happened.
**Severity:** medium

### FE-10 — Tab/role-switch mid-fill on signup
**Category:** edge
**Input Scenario:** Partially fill the candidate signup form, switch to the recruiter tab, switch back.
**Expected Behavior:** No field-state bleed between the two forms.
**Severity:** medium

### FE-11 — Submit before CV upload/parse completes
**Category:** race-condition
**Input Scenario:** Click Submit immediately after selecting a CV file, before any upload/preview step finishes.
**Expected Behavior:** No race between "still uploading" and "form submitted" — submit either waits or is disabled until the file is genuinely attached.
**Severity:** high

### FE-12 — Manually tampered session state mid-session
**Category:** adversarial
**Input Scenario:** Edit `sessionStorage.userType` from `candidate` to `recruiter` (or delete `candidateId`/`recruiterId` entirely) via devtools while on an authenticated page, without re-navigating.
**Expected Behavior:** App detects the inconsistent state on next render/route guard and forces re-auth.
**Failure Mode:** Given the confirmed total absence of server-side session validation, `sessionStorage` is **the only place "who am I" is recorded at all** — there is no server-side cross-check that could ever catch this tampering being wrong, because the server never independently knows who the user is in the first place; it only ever receives whatever ID the (now-tampered) client chooses to send. This is the frontend manifestation of `SL-SB-01`.
**Severity:** critical

### FE-13 — Back button immediately after signin
**Category:** edge
**Input Scenario:** Browser back button right after a successful signin redirect.
**Expected Behavior:** No ambiguous logged-in-on-login-page state.
**Severity:** medium

---

## 3. Job Listing, Filters & Apply Dialog

### FE-14 — Salary filter min > max
**Category:** edge
**Input Scenario:** Set min=200000, max=50000.
**Expected Behavior:** Auto-correct or clear validation message — never a silent zero-result with no explanation.
**Severity:** medium

### FE-15 — Filter combination matching zero jobs
**Category:** normal
**Input Scenario:** Apply filters that legitimately match nothing.
**Expected Behavior:** Clear "no results" state.
**Severity:** low

### FE-16 — File upload above the 5MB backend cap
**Category:** edge
**Input Scenario:** Select a 6MB+ file for CV upload.
**Expected Behavior:** Client-side rejection before the network request fires, with a clear message — not a slow upload that fails late with a generic 413.
**Severity:** high

### FE-17 — Non-PDF file selection
**Category:** abuse
**Input Scenario:** Select/force-select a `.docx`, `.txt`, or renamed `.exe` for CV upload.
**Expected Behavior:** `accept` attribute constrains the file picker; if bypassed (drag-drop, devtools), a client-side type check still catches it before upload.
**Severity:** medium

### FE-18 — Apply dialog open across job expiry
**Category:** edge
**Input Scenario:** Job expires while the Apply dialog sits open; candidate submits anyway.
**Expected Behavior:** Clean rejection on stale submit (backend independently revalidates expiry — confirmed fixed this engagement).
**Severity:** medium

---

## 4. My Applications / Application Cards

### FE-19 — Zero applications empty state
**Category:** normal
**Input Scenario:** Candidate with no applications views `/my-applications`.
**Expected Behavior:** Clean empty state; filter panel doesn't crash deriving options from an empty dataset.
**Severity:** medium

### FE-20 — Unrecognized application status value
**Category:** edge
**Input Scenario:** An application has a status value not present in `STATUS_LABELS`/`STATUS_VARIANTS` (e.g. a future backend status added without a frontend update).
**Expected Behavior:** Fallback (`?? status`, `?? 'pending'`) renders something legible, not `undefined` or a blank badge.
**Severity:** low

### FE-21 — Stale `application_id` navigation after list re-filter
**Category:** edge
**Input Scenario:** Apply a filter that reorders the list, then click "Check Application" on a card.
**Expected Behavior:** Navigates to the correct `application_id` for the card actually clicked, not a stale index-based reference.
**Severity:** medium

---

## 5. Application Progress Page

### FE-22 — Fabricated `applicationId` in URL
**Category:** adversarial
**Input Scenario:** Manually navigate to `/application-progress/00000000-0000-0000-0000-000000000000`.
**Expected Behavior:** Clean "not found" state.
**Failure Mode:** Per the confirmed backend IDOR (SL-29), a *real-but-not-yours* `applicationId` here doesn't 404 at all — it successfully loads someone else's interview progress. This case specifically isolates the "totally fake ID" sub-case to separate "crashes on garbage input" (a frontend robustness bug) from "succeeds on someone else's real input" (the backend authorization bug) — both are real, but need to be tested and reported as the distinct issues they are.
**Severity:** high (fake ID) / critical (real-but-foreign ID, via SL-29)

### FE-23 — `Not Needed` round rendering
**Category:** normal
**Input Scenario:** View a round with status `Not Needed`.
**Expected Behavior:** Muted badge, non-clickable, correct explanatory copy (implemented this engagement).
**Severity:** low (regression-guard)

### FE-24 — `HIRED` terminal state rendering
**Category:** normal
**Input Scenario:** View an application with status `HIRED`.
**Expected Behavior:** Clear positive terminal state, "Go To Interview Room" CTA hidden.
**Severity:** medium

### FE-25 — Resume in-progress interview vs. restart
**Category:** edge
**Input Scenario:** Click into an interview, browser-back to Application Progress, click in again.
**Expected Behavior:** Resumes the same in-progress interview; does not re-trigger question generation against an already-`In Progress` interview.
**Severity:** high

---

## 6. Interview Room

### FE-26 — Network drop mid-written-interview
**Category:** stress
**Input Scenario:** Lose connectivity for 30+ seconds mid-answer, then reconnect.
**Expected Behavior:** No answer loss (local draft state survives); timer behavior is sane and not exploitable to gain extra time.
**Severity:** critical

### FE-27 — Refresh/close-reopen mid-written-interview
**Category:** abuse
**Input Scenario:** F5 refresh, or close-and-reopen the tab, mid-interview.
**Expected Behavior:** Treated as a leave event server-side — cannot be used to dodge `report-leave` or reset a question the candidate is struggling with.
**Severity:** high

### FE-28 — OS-level mic mute mid-voice-interview
**Category:** abuse
**Input Scenario:** Mute at the OS/browser level (not LiveKit's own mute control), stay silently "connected."
**Expected Behavior:** Server-side fail-safe timeout exists independent of client-reported mic state.
**Severity:** high

### FE-29 — Extremely long written answer
**Category:** stress
**Input Scenario:** 10,000+ characters into a written-answer textarea.
**Expected Behavior:** No client freeze/lag; no silent hidden-`maxlength` truncation the user isn't warned about.
**Severity:** medium

### FE-30 — Direct devtools manipulation of the score-answers request
**Category:** adversarial
**Input Scenario:** From the browser console, on the Interview Room page, manually replay the score-answers `fetch()` call with a different `interview_id` than the one currently loaded.
**Expected Behavior:** Rejected server-side regardless of what the frontend sends.
**Failure Mode:** This is a manual, low-effort reproduction of the confirmed SL-29/SL-21 backend IDOR — flagged specifically because the page **already has the current interview's `interview_id` sitting in component state/the URL**, and `DebugBreadcrumb` (if its production-gating issue isn't fixed) hands the user a worked example of the ID format on every other page they've visited. The frontend makes discovering this trivial; it does nothing to prevent exploiting it once discovered, since there's no client-side concept of "this isn't your interview" either (the page would happily render whatever `interview_id` is in the URL, same gap as FE-22).
**Severity:** critical

### FE-31 — Timer hits zero mid-answer
**Category:** edge
**Input Scenario:** Let the countdown reach 0 while an answer is unsubmitted.
**Expected Behavior:** Clear auto-submit or "time's up" state — never a silent freeze where the candidate can't tell if their answer was captured.
**Severity:** high

### FE-32 — Tab-switch detection consistency across interview types
**Category:** edge
**Input Scenario:** Switch tabs mid-written-interview; compare behavior to the documented voice-interview tab-switch handling.
**Expected Behavior:** Consistent policy across both interview types, or an explicit documented reason for any difference.
**Severity:** medium

---

## 7. Recruiter Dashboard

### FE-33 — Round-order recalculation on mid-list removal
**Category:** edge
**Input Scenario:** Build a 10+ round list, remove a round from the middle.
**Expected Behavior:** `round_order` recalculated cleanly (no gaps/duplicates) before submission — feeds directly into the confirmed-risky SL-07 backend gap, so the frontend must not be the only thing preventing bad data here.
**Severity:** high

### FE-34 — Duplicate round type in the builder
**Category:** edge
**Input Scenario:** Add "Written Technical" twice.
**Expected Behavior:** Either blocked with a clear message, or genuinely supported and rendered as two distinct entries — never silently merged/hidden.
**Severity:** medium

### FE-35 — Bypassing `type="number"` on `failing_criteria`
**Category:** abuse
**Input Scenario:** Paste non-numeric text into the field, or strip the `type="number"` attribute via devtools and enter out-of-range values.
**Expected Behavior:** Client-side guard rejects it independent of the backend's 0-100 Pydantic validator (defense in depth, not reliance on the backend alone).
**Severity:** high

### FE-36 — Past-date `expires_at` via the date picker
**Category:** abuse
**Input Scenario:** Attempt to select a past date.
**Expected Behavior:** Picker blocks past dates, or a clear validation error appears — frontend half of the confirmed-missing SL-06 backend check, meaning right now this is the *only* defense that exists at all.
**Severity:** high

### FE-37 — Zero-applicant job stats page
**Category:** normal
**Input Scenario:** View `/job-stats` immediately after posting, before any applications exist.
**Expected Behavior:** No crash on empty-applicants state.
**Severity:** low

---

## 8. Job Post Stats Page

### FE-38 — Rapid candidate-dialog switching before first load resolves
**Category:** race-condition
**Input Scenario:** Open candidate A's dialog, immediately close it, open candidate B's dialog before A's `fetchCandidatePanel` call resolves.
**Expected Behavior:** No stale-closure mixing — B's dialog never briefly or permanently shows A's data.
**Failure Mode:** Needs live verification of whether the async fetch's resolution is guarded against the dialog having since been closed/reopened for a different candidate (a classic React stale-closure bug pattern: an in-flight promise from the first selection resolving after a second selection has already updated state).
**Severity:** high

### FE-39 — Large candidate list rendering performance
**Category:** stress
**Input Scenario:** Expand a round with 50+ candidates.
**Expected Behavior:** Sane scroll/render performance, no unbounded DOM list causing lag.
**Severity:** medium

### FE-40 — Special characters / unicode in candidate names
**Category:** edge
**Input Scenario:** Candidate name contains `<script>`-like text or unusual unicode.
**Expected Behavior:** React's default escaping holds; no `dangerouslySetInnerHTML` used anywhere for user-supplied display text.
**Severity:** low (very unlikely to be broken, worth a one-time grep-confirm)

### FE-41 — `Not Needed` candidate Q&A click
**Category:** normal
**Input Scenario:** Click a round entry for a candidate whose status is `Not Needed`.
**Expected Behavior:** Correctly non-clickable.
**Severity:** low (regression-guard)

---

## SYSTEM BREAK SCENARIOS (Frontend)

### FE-SB-01 — Frontend is the entire security boundary, and it's trivially bypassable
**Category:** adversarial / system-break
**Input Scenario:** Treat the frontend as advisory only — drive every state transition in the system (apply, score, post job, view analytics) via direct `fetch()` calls with arbitrary IDs and payloads, never touching the rendered UI at all.
**Expected Behavior:** The backend independently enforces every business rule and ownership boundary the frontend appears to enforce.
**Failure Mode:** It does not, for the confirmed IDOR/no-session-layer reasons documented exhaustively in `system_logic_test_cases.md`. The practical consequence for the frontend specifically: **every client-side validation, disabled button, hidden CTA, and route guard in this codebase is a UX courtesy, not a security control.** This isn't a single bug to fix in the frontend — it's the reason the frontend test cases above (FE-01, FE-04, FE-12, FE-22, FE-30) keep converging on the same backend root cause. Flagged as its own system-break entry because it reframes how every other frontend finding in this file should be triaged: don't fix the frontend symptom in isolation and consider it closed.
**Severity:** critical

### FE-SB-02 — Cascading UI desync after a backend cascade fires asynchronously
**Category:** edge / system-break
**Input Scenario:** Candidate has the Application Progress page open in one tab while their interview is being scored (e.g. a recruiter or an automated process triggers scoring via another path, or the candidate's own voice-interview scoring completes asynchronously after they've already navigated back). The `_mark_subsequent_rounds_not_needed`/`_maybe_mark_hired` cascades fire server-side, but the already-loaded page has stale `data` in React state from before the cascade.
**Expected Behavior:** The page either polls/refreshes to reflect the new state, or clearly indicates the displayed data may be stale and offers a refresh.
**Failure Mode:** `ApplicationProgress.tsx` fetches stage data once on mount (confirmed pattern: `useEffect` on `applicationId`) with no polling/websocket/SSE-driven live-update mechanism for the *stages* data itself (the `status-stream` SSE is interview-completion-specific, not a general stage-state subscription). A candidate could be looking at a page that says "Round 2: Scheduled" when the backend has already cascaded that round to `Not Needed` because round 1 was just scored Failed by a process they can't see — clicking "Go To Interview Room" on stale-but-displayed-as-available data would hit the backend's `Not Needed` guard and fail, but the *reason why* would be confusing without a stale-data explanation.
**Severity:** medium

### FE-SB-03 — Catastrophic layout failure compounds with a backend failure during the same incident
**Category:** stress / system-break
**Input Scenario:** Backend goes down (deploy, crash, DB outage) while multiple candidates are mid-interview across the platform — combine `FE-26`/`FE-31`(network drop, timer edge cases) with simultaneous occurrence across every active session, not just one.
**Expected Behavior:** Every affected page independently fails gracefully and recoverably — no candidate permanently loses interview progress because of an infrastructure incident unrelated to their own actions.
**Failure Mode:** Each individual page's error-handling was flagged in the prior round's report as needing live verification (`FE-49` in the original report) — restated here as a system-break case because the *aggregate* failure mode under a real incident (every active candidate simultaneously) is qualitatively different from one candidate's network blip: it's the moment a production incident either stays "annoying, some retries needed" or becomes "we silently lost N candidates' interview data during the outage window," and nothing in the current architecture (no draft-answer persistence beyond component state, no resumable-interview concept per `VA-SB-01`) suggests the latter is avoided.
**Severity:** critical
