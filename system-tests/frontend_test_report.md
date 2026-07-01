# Frontend — Test Report (v2)

**Companion to:** `frontend_test_cases.md`
**Method:** Static code audit (Grep/Read across `frontend/src/`). No live browser session
was driven for this report (Playwright/manual-browser execution intentionally deferred
per project decision). Each finding includes **Input payload**, **API/module involved**,
**Expected vs. Actual**, **Severity**, **Suggested fix (architectural-level preferred)**.

---

## Severity Summary

| Severity | Confirmed | Not Yet Executed |
|---|---|---|
| CRITICAL | 2 | 5 |
| HIGH | 0 | 13 |
| MEDIUM | 0 | 17 |
| LOW | 0 | 6 |

---

## CONFIRMED Findings

### F-FE-01 (FE-46 / FE-SB-01) — Debug IDs panel hardcoded on in production, directly enables the confirmed backend IDOR
**Severity:** CRITICAL

**Input payload:** Any authenticated session, any page — no special input required, this is a rendering-by-default issue.

**API / module involved:** `frontend/src/components/DebugBreadcrumb.tsx:6` (`const SHOW_DEBUG_BREADCRUMB = true`), mounted globally in `App.tsx`.

**Expected vs. Actual:**
- Expected: invisible/disabled in production builds, gated behind `import.meta.env.DEV` or an equivalent build-mode flag.
- Actual: renders identically in production. Every logged-in user sees a "{ }" button exposing their own `recruiter_id`/`job_post_id` (recruiter pages) or `candidate_id`/`application_id`/`interview_id`/`job_post_id` (candidate pages) in plain, copyable text.

**Suggested fix (architectural):** Gate behind `import.meta.env.DEV` so it's automatically stripped from production builds by Vite's own build process, rather than depending on a manually-toggled source constant someone has to remember to flip before every release. This is a one-line fix but is filed as CRITICAL specifically because of its *compounding* effect: it directly lowers the skill floor for exploiting `F-SL-01` through `F-SL-04` in `system_logic_test_report.md` from "guess a UUID" to "read it off your own screen, or a teammate's, or a support screenshot." **Should ship in the same change as the backend session-auth fix, not before it** — fixing this alone still leaves the backend IDOR exploitable by anyone who finds IDs another way (screenshots, browser history, network logs); fixing the backend alone without this still leaves casual/accidental misuse trivially easy.

---

### F-FE-02 (cross-referenced from system logic root cause) — No client-side concept of "this resource isn't mine," because the backend has none either
**Severity:** CRITICAL

**Input payload:** Any page that renders data scoped to an `application_id`/`interview_id`/`job_id` from the URL — `ApplicationProgress.tsx`, `InterviewRoom.tsx`, `JobPostStats.tsx`.

**API / module involved:** All three pages' data-fetching `useEffect` hooks, which call their respective `api/*.ts` functions with whatever ID is in the URL/route params, with no ownership pre-check before rendering the response.

**Expected vs. Actual:**
- Expected: a page should refuse to render (or should never even successfully fetch) data for a resource the logged-in user doesn't own.
- Actual: each page will happily render whatever the backend returns for the ID in the URL — and per the confirmed backend IDOR, the backend returns real data for IDs that aren't the caller's. This isn't a separate frontend bug to fix in isolation (there's no missing frontend check that would meaningfully help — the *backend* response itself contains the unauthorized data by the time the frontend has it), but it's recorded here because it's the direct, observable symptom a tester would see when manually walking through `FE-22`/`FE-30`'s reproduction steps, and because once the backend fix lands, these pages' error-state handling (what do they render on a 403?) becomes a real, separate frontend requirement worth testing on its own.

**Suggested fix (architectural):** No frontend-only fix meaningfully closes this — it's downstream of the backend root cause (see `system_logic_test_report.md`'s Architectural Fix section). Once the backend returns 403 for unauthorized access, audit `ApplicationProgress.tsx`/`InterviewRoom.tsx`/`JobPostStats.tsx`'s error-handling paths specifically for the *new* 403 case (likely currently only handles "not found"/network-error shaped failures, not "exists but isn't yours") to ensure it renders a clear access-denied state rather than however a generic fetch-error branch currently behaves for an unexpected status code.

---

## NOT YET EXECUTED — Requires a Live Browser Session

| ID | Severity | What to check |
|---|---|---|
| FE-01, FE-04 | high, high | Direct-API and attribute-stripping form bypass on every required field across signup/job-post/apply |
| FE-02 | high | Double-click Apply debounce — verify a client-side in-flight guard exists at all |
| FE-03 | critical | Optimistic-UI-vs-actual-response check on Apply — **highest priority in this file**, silent false-positive "Applied" state would be a severe trust-breaking bug if confirmed |
| FE-05 | medium | Offline-then-retry apply behavior |
| FE-06–FE-13 | medium (×6), high, critical | Auth form validation boundaries; tampered `sessionStorage.userType` mid-session (**FE-12, run early** — directly tests the frontend face of the no-session-layer root cause) |
| FE-14–FE-18 | medium ×3, high, medium | Filter edge cases; oversized/wrong-type file upload; stale-expiry apply submission |
| FE-19–FE-21 | medium, low, medium | Empty-state rendering; unrecognized status fallback; post-filter navigation correctness |
| FE-22 | high / critical | Fabricated vs. real-but-foreign `applicationId` — **run both halves separately**, they test different bugs (frontend robustness vs. confirmed backend IDOR) |
| FE-25–FE-29 | high, critical, high, high, medium | Interview resume-vs-restart; network-drop answer persistence (**FE-26, high priority** — direct candidate-trust impact); refresh-as-leave-dodge; OS-mute fail-safe; long-answer handling |
| FE-30 | critical | Manual devtools score-answers replay with a foreign `interview_id` — direct reproduction of the confirmed backend score-tampering primitive |
| FE-31, FE-32 | high, medium | Timer-zero auto-submit state; cross-interview-type tab-switch policy consistency |
| FE-33–FE-37 | high, medium, high, high, low | Recruiter round-builder edge cases — all five feed directly into confirmed-or-unconfirmed backend gaps (`SL-07`, `SL-06`), meaning right now the frontend may be the *only* defense for several of these |
| FE-38, FE-39 | high, medium | Stale-closure candidate-dialog race; large-list render performance |
| FE-40, FE-41 | low, low | XSS-escaping spot-check (quick grep-confirm, not even necessarily a browser test); Not-Needed click-guard regression |
| FE-SB-02, FE-SB-03 | medium, critical | Stale-stage-data-after-async-cascade UX; aggregate incident-scale failure behavior across simultaneous active interviews |

**Priority recommendation:** FE-03 (silent false "Applied" state) and FE-30 (manual
reproduction of the confirmed backend score-tampering bug) first — both are cheap to
check by hand in a browser and both directly validate/invalidate severe findings from
this and the system-logic report. FE-12 third, since it's the cleanest single
demonstration of the no-session-layer root cause from the frontend side, useful for
building a concrete reproduction to hand to whoever implements the architectural fix.
