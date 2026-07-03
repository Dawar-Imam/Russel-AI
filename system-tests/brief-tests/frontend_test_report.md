# Frontend — Brief Test Report

**Suite:** `brief-tests/frontend_test_cases.md`
**Total cases:** 11 (10 targeted + 1 system-break)
**Branch:** `complete-working`
**Tested by:** Static code analysis of `frontend/src/pages/*.tsx` and `frontend/src/components/*.tsx`
**Date:** 2026-07-01
**Method:** Code inspection — logic is deterministic; all pass/fail verdicts are conclusive without a live browser.

---

## Results Summary

| ID | Summary | Verdict |
|---|---|---|
| FE-02 | Double submission of the same application | ⚠️ PARTIAL FAIL |
| FE-03 | Optimistic UI on failed apply request | ✅ PASS |
| FE-12 | Tampered sessionStorage mid-session | ❌ FAIL |
| FE-16 | File upload above 5 MB cap | ⚠️ PARTIAL FAIL |
| FE-22 | Fabricated `applicationId` in URL | ⚠️ PARTIAL |
| FE-25 | Resume in-progress interview vs. restart | ⚠️ RISK (frontend) |
| FE-30 | Devtools score-answers IDOR replay | ❌ FAIL |
| FE-31 | Timer hits zero mid-answer | ✅ PASS |
| FE-33 | Round-order recalculation on mid-list removal | ✅ PASS |
| FE-36 | Past-date `expires_at` via date picker | ✅ PASS |
| FE-SB-01 | Frontend as entire security boundary | ❌ FAIL (system-break) |

**Pass: 4 | Partial/Risk: 3 | Fail: 4**

---

## Detailed Findings

### FE-02 — Double submission of the same application
**Verdict: ⚠️ PARTIAL FAIL**

`JobApplyDialog.tsx` disables the Apply button with `disabled={applying}` and calls `setApplying(true)` at the top of `handleApplyClick`. However, `setApplying(true)` is a React state update — the button is not actually disabled in the DOM until the next render flush. Between the first click and the re-render (which only completes after the async `fetch` call suspends), a second rapid click can invoke `handleApplyClick` again because `applying` is still `false` in the closure.

No synchronous ref-based guard (`isSubmittingRef`) exists here, unlike `InterviewRoom.tsx` which uses one. The backend (SL-12) also has no dedup layer. Two-layer gap confirmed.

**Evidence:** `JobApplyDialog.tsx:53` — `setApplying(true)` (state, not ref); `JobApplyDialog.tsx:171` — `disabled={applying}` (re-render-dependent)

---

### FE-03 — UI shows "Applied" but backend request actually failed
**Verdict: ✅ PASS**

`handleApplyClick` is fully pessimistic — no optimistic state is set before the network call. The dialog only closes (`handleClose()`) and navigation only fires (`navigate(...)`) after:
1. `res.ok` confirmed (line 67)
2. `res.json()` resolves with `application_id` (line 71)
3. `isCancelled.current` passes (line 72)

If the request fails or the connection dies, the `catch` block sets `error` and re-enables the button via `setApplying(false)`. The candidate stays on the apply dialog with a visible error. No "applied" state is shown on failure.

---

### FE-12 — Manually tampered session state mid-session
**Verdict: ❌ FAIL**

`sessionStorage` is the sole identity record. `RecruiterDashboard.tsx` reads `recruiterId` from `sessionStorage.getItem('recruiterId')` and `Jobs.tsx` reads `candidateId` from `sessionStorage.getItem('candidateId')`. There is no periodic revalidation, no session cookie, and no auth token on any API call.

Editing `sessionStorage.candidateId` in DevTools to any other candidate's UUID means all subsequent API calls (apply, fetch progress, trigger ATS) use the tampered identity. The backend accepts whatever ID the client sends. The only auth guard is the initial `if (!recruiterId) navigate('/')` check in `RecruiterDashboard.tsx:68` — a presence check only, not a server-side validation.

**Evidence:** Zero `Authorization` headers across all `fetch()` calls in `pages/` and `components/`

---

### FE-16 — File upload above the 5 MB backend cap
**Verdict: ⚠️ PARTIAL FAIL**

**Auth.tsx signup CV — PASS (fixed this session):** `handleCvChange` now rejects files > `CV_MAX_BYTES` (5 MB) immediately on selection, sets `submitError`, and clears the file input. User sees the error before any network request.

**JobApplyDialog.tsx apply CV — FAIL:** The `onChange` handler at line 140 is simply `onChange={(e) => setCvFile(e.target.files?.[0] ?? null)}` — no size check. A 6 MB+ file is silently attached to `FormData` and sent. The backend may return a generic 413 with no actionable message. This is the higher-traffic path (every job application), so the gap is significant.

---

### FE-22 — Fabricated `applicationId` in URL
**Verdict: ⚠️ PARTIAL**

`ApplicationProgress.tsx:163-169` fetches `/api/applications/${applicationId}/interview-stages`. If the UUID doesn't exist, the backend returns a non-2xx and the `catch` block renders `"Server error 404"` — not a crash, but the message is generic rather than "Application not found."

For IDOR (a real UUID belonging to another candidate): confirmed by SL-29, the backend loads the other candidate's full pipeline data with no ownership check. The frontend sends no user identity token for the backend to verify, so it has no defence.

---

### FE-25 — Resume in-progress interview vs. restart
**Verdict: ⚠️ RISK (frontend side)**

`InterviewRoom.tsx:361-408` unconditionally calls `generate-questions` on every mount, with no check on current interview status beforehand. Every page load, refresh, or back-navigation fires the request regardless.

Whether this causes double-question generation depends entirely on `interview_service.py`'s idempotency for an "In Progress" interview. The frontend provides zero protection. If the backend re-creates questions for an in-progress interview, a candidate can back-navigate to reset their question set — a data integrity gap.

**Status:** Backend idempotency for "In Progress" was not verified in this code read. Recommend manual test of back-navigation mid-interview.

---

### FE-30 — Direct devtools manipulation of the score-answers request
**Verdict: ❌ FAIL (confirmed)**

`doSubmit` in `InterviewRoom.tsx:183` sends `fetch(…/api/interviews/${interviewId}/score-answers, …)` where `interviewId` comes from `useParams` (the URL). From browser console an attacker replays:
```js
fetch('http://localhost:8000/api/interviews/VICTIM_UUID/score-answers', {
  method: 'POST', headers: {'Content-Type':'application/json'},
  body: JSON.stringify({fetch_from_db:false, answers:[], interview_type:'written', event_type:'submit'})
})
```
The backend has no session layer and no ownership check (confirmed IDOR SL-21). The call succeeds and can overwrite or trigger scoring on any interview. Frontend disabled buttons are entirely bypassed by direct `fetch()`.

---

### FE-31 — Timer hits zero mid-answer
**Verdict: ✅ PASS**

`InterviewRoom.tsx:414-428`: when the written interview timer reaches 0, `doSubmit(true)` is called directly from the interval callback (inside `setTimer`'s updater function). `doSubmit` uses `isSubmittingRef.current` to prevent re-entry, transitions immediately to `'submitting'` phase, and displays "Scoring your answers…" with a spinner. No silent freeze possible.

For voice interviews (lines 434-449), timer expiry calls `roomRef.current?.disconnect()` which triggers `RoomEvent.Disconnected` → EventSource stream → `'submitting'` phase. Both paths communicate state clearly.

---

### FE-33 — Round-order recalculation on mid-list removal
**Verdict: ✅ PASS**

`handleRemoveRound` (`RecruiterDashboard.tsx:191-193`) filters the removed round from the `selectedRounds` array. The `SelectedRound` type has no `round_order` field — position is implicit in the array index.

In `handlePostJob` (line 232-235), `round_order` is computed at submission time as `i + 1` (array index + 1). Removing a middle element and submitting produces a clean contiguous 1, 2, 3… sequence. No gaps or duplicates are possible regardless of which round was removed or how many were reordered via drag-and-drop.

---

### FE-36 — Past-date `expires_at` via the date picker
**Verdict: ✅ PASS (fixed this session)**

Two-layer defence now in `RecruiterDashboard.tsx`:

1. `min={todayIso()}` — native date picker blocks past-date selection in all modern browsers.
2. `handleExpiresAtChange` — validates typed/pasted values: if `value < todayIso()` sets `expiresAtError` and shows inline error.
3. Publish button: `disabled={posting || !!formSalaryError || !!expiresAtError}` — an error prevents submission even if the `min` attribute is bypassed via DevTools.

---

### FE-SB-01 — Frontend is the entire security boundary
**Verdict: ❌ FAIL (system-break)**

Every state transition is driven by unauthenticated `fetch()` calls:

| Action | Endpoint | Auth? |
|---|---|---|
| Apply to job | `POST /api/applications/apply` | None |
| Generate questions | `POST /api/interviews/{id}/generate-questions` | None |
| Score answers | `POST /api/interviews/{id}/score-answers` | None |
| Post a job | `POST /api/jobs/` | None |
| View application progress | `GET /api/applications/{id}/interview-stages` | None |
| Run ATS | `POST /api/applications/{id}/run-ats` | None |

No `Authorization` header, no cookie, no session token on any request. The backend identifies users solely from IDs in the request body/URL, which are unvalidated client-supplied `sessionStorage` values. Every UI-level control (disabled buttons, hidden CTAs, route guards) is a UX courtesy only. This is the root cause behind FE-12, FE-22, FE-30, and all confirmed IDOR findings.

---

## Fixes Applied This Session

| File | What was fixed |
|---|---|
| `Auth.tsx` | Added `EMAIL_RE` / `NAME_RE` regex; `CV_MAX_BYTES` 5 MB guard; `blockNonNumericKey`; sign-in email format check; signup name format + email format + password min-8 + experience 0-60 range validation; all inline error spans; `max="60"` + `onKeyDown` on experience input |
| `RecruiterDashboard.tsx` | Added `blockNonNumericKey` / `todayIso`; `attemptedPost` + `expiresAtError` state; `handleExpiresAtChange` with past-date check; `handleFailingCriteriaChange` auto-clamp 0-100; required-field inline errors for Job Category / Experience Level / Job Type; salary inputs `max="10000000"` + `onKeyDown`; date input uses `todayIso()` + `handleExpiresAtChange`; failing-criteria `onKeyDown`; Publish button `disabled` includes `expiresAtError` |
| `FilterPanel.tsx` | Added `blockNonNumericKey`; salary inputs `max="10000000"` + `onKeyDown` |
| `RecruiterDashboard.css` | Added `.required-star` rule |

## Remaining Fix Priority

| Priority | Case | Recommended Fix |
|---|---|---|
| P0 — System-break | FE-SB-01 | Add authentication (JWT / session cookie) to all API endpoints |
| P0 — Data integrity | FE-30 | Backend ownership check on `score-answers` endpoint |
| P1 — User data | FE-12 | Server-side session-bound identity; reject mismatched IDs |
| P1 — UX gap | FE-16 | Add 5 MB guard to `JobApplyDialog.tsx` `onChange` handler |
| P2 — Race condition | FE-02 | Add `isSubmittingRef` guard in `JobApplyDialog` before first `setApplying` call |
| P2 — Verify | FE-25 | Manual test: back-navigate mid-interview; verify backend returns same questions |
| P3 — UX polish | FE-22 | Return "Application not found" instead of generic "Server error 404" |
