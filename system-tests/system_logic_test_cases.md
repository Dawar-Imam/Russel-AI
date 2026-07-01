# System Logic — End-to-End & Adversarial Test Cases (v2)

Scope: full candidate + recruiter journey across `backend/app/services/*.py` and their
HTTP endpoints — auth, job posting, applying, multi-round interview progression,
ATS/HIRED/Not-Needed state machine, recruiter analytics, authorization boundaries.

**Root-cause note, established up front because it shapes how to read every case below:**
a full grep of `backend/app/api/` and `backend/app/services/auth_service.py` for any
session/token mechanism (`Depends`, JWT, `Authorization` header, session cookie) returned
**zero results**. There is no server-side session enforcement anywhere in this backend.
Every endpoint trusts whatever `candidate_id`/`recruiter_id`/`application_id`/
`interview_id`/`job_id` the client sends as a plain request parameter. This is not a
per-endpoint bug to patch one at a time — it is the single architectural root cause
behind nearly every "session hijacking," "IDOR," and "bypass eligibility via API
manipulation" case in this file. Treat individual fixes below as mitigations; the real
fix is listed once, in the System Break section and the report.

## Required Fields (every case)

Test Case ID · Category (`normal` / `edge` / `abuse` / `adversarial` / `stress` /
`race-condition`) · Input Scenario · Expected Behavior · Failure Mode · Severity
(`low` / `medium` / `high` / `critical`)

---

## 1. Sign Up / Sign In

### SL-01 — Same email across candidate and recruiter roles
**Category:** edge
**Input Scenario:** Sign up a candidate with `user@test.com`, then sign up a recruiter with the same exact email.
**Expected Behavior:** Second signup rejected with a clear "email already in use" error, OR the system explicitly supports one email holding both roles with no `userType` ambiguity at signin.
**Failure Mode:** If `Users` table uniqueness is enforced on email but `userType` resolution at signin doesn't deterministically pick one role, the same credentials could route to different dashboards on different signins, or one role's data could be exposed through the other's session context.
**Severity:** high

### SL-02 — Credential brute-force with no lockout
**Category:** abuse
**Input Scenario:** Script 50+ signin attempts against one email with random wrong passwords, no delay between attempts.
**Expected Behavior:** Rate limiting or progressive lockout after N failed attempts; consistent response timing/messaging regardless of whether the account exists (no enumeration signal).
**Failure Mode:** No rate-limiting or lockout middleware was found anywhere in `auth_service.py`/`api/endpoints/auth.py`. Combined with no session/token layer at all (see root-cause note), a successful brute-force directly grants the same trust level as legitimate login — i.e., a raw ID the client can then use everywhere else in the system with zero further verification.
**Severity:** critical

### SL-03 — Email normalization gaps
**Category:** edge
**Input Scenario:** Sign up with `User@Test.com`, then attempt to sign up again with `user@test.com` or `user@test.com ` (trailing space).
**Expected Behavior:** Treated as the same email; second signup rejected as duplicate.
**Failure Mode:** If normalization (lowercase + trim) isn't applied consistently before the uniqueness check, two "different" rows could exist for what a human considers one email, fragmenting that person's identity across two accounts with no way to merge.
**Severity:** medium

### SL-04 — SQL injection payloads through auth fields
**Category:** adversarial
**Input Scenario:** Submit `' OR '1'='1`, `'; DROP TABLE Users; --`, and similar payloads in every signup/signin text field.
**Expected Behavior:** Inert — treated as literal string content, no query structure alteration.
**Failure Mode:** Prior audit confirmed parameterized `?` queries throughout `services/*.py` generally; this case exists to specifically re-verify `auth_service.py` wasn't missed in that audit (different file, written possibly at a different time than the rest of the service layer).
**Severity:** critical (if found), otherwise confirms safe

### SL-05 — Recruiter signup with a long/empty `company_name`
**Category:** edge
**Input Scenario:** Sign up a recruiter with `company_name` either empty/whitespace, or 5,000+ characters.
**Expected Behavior:** Empty rejected per documented `@field_validator` empty-check; oversized either truncated or rejected with a clear error, not silently stored and breaking downstream UI (job cards display company name with no visible truncation logic confirmed).
**Severity:** low

---

## 2. Recruiter Posts a Job

### SL-06 — Job posted with `expires_at` already in the past
**Category:** abuse
**Input Scenario:** `POST /jobs` with `expires_at` set to yesterday's date.
**Expected Behavior:** Rejected at creation with a clear validation error — a recruiter should never be able to publish a pre-expired listing.
**Failure Mode:** No `expires_at >= today` validator was found in `JobPostRequest` (`schemas/jobs.py`) — only candidate-side queries filter expired jobs out of visibility; nothing stops creation of an already-invalid job, which is silently uninteractable (never shown, never applyable) from the moment it's created, with no error surfaced to the recruiter explaining why their new posting has zero applicants.
**Severity:** medium

### SL-07 — Non-sequential / duplicate `round_order` values
**Category:** edge
**Input Scenario:** Post a job with rounds `[{round_order: 1}, {round_order: 1}, {round_order: 5}]` (duplicate + gap).
**Expected Behavior:** Either rejected with a validation error, or auto-normalized to `[1, 2, 3]` server-side before storage.
**Failure Mode:** No round_order uniqueness/sequentiality validation found in `InterviewRoundInput` (`schemas/jobs.py:11-23`) or `post_job`. Directly threatens the correctness of `_maybe_mark_hired`'s "no later active round" check and `get_interview_stages`'s `current_round_id` resolution, both of which reason about round_order ordering — undefined behavior with duplicate/non-sequential values, not just a cosmetic data-quality issue.
**Severity:** high

### SL-08 — `failing_criteria` boundary and bypass values
**Category:** abuse
**Input Scenario:** POST a job via raw API call (bypassing the frontend form entirely) with `failing_criteria: -50`, `failing_criteria: 999`, `failing_criteria: null`.
**Expected Behavior:** `-50`/`999` rejected (0-100 enforced server-side per the existing Pydantic validator); `null` accepted (optional field, no failing threshold = always pass this round on completion).
**Failure Mode:** Pydantic validator confirmed present (`schemas/jobs.py`) — included here as a direct-API-bypass regression case to confirm the frontend isn't the only enforcement layer (it explicitly is not, by design, but worth a standing test).
**Severity:** medium

### SL-09 — Job with zero interview rounds — hire path verification
**Category:** edge
**Input Scenario:** Post a job with `interview_rounds: []`. Candidate applies, passes ATS.
**Expected Behavior:** Candidate is marked `HIRED` immediately upon ATS pass (per the recruiter UI's own stated copy: "Candidates will proceed directly to hiring").
**Failure Mode:** **Confirmed structural gap** (cross-referenced from `ai_test_report.md`): `_maybe_mark_hired` only fires from `_save_scores_and_complete` on a round being scored `Pass` — a zero-round job has no round-scoring event ever, so this candidate's `Applications.status` stays at `ATS_PASS` forever, contradicting the recruiter-facing promise made in the UI copy.
**Severity:** high

### SL-10 — Tampered `recruiter_id` in job-post payload
**Category:** adversarial
**Input Scenario:** Recruiter A is logged in (their `recruiter_id` in `sessionStorage`), but edits the `POST /jobs` request body in devtools to set `recruiter_id` to Recruiter B's ID before sending.
**Expected Behavior:** Rejected — `recruiter_id` should be derived from an authenticated session server-side, never trusted from the client body.
**Failure Mode:** Per the root-cause note, there is no session layer at all — `recruiter_id` in `JobPostRequest` is just a plain field. **This succeeds.** A job gets created attributed to Recruiter B (who never asked for it, never approved it, and now has an unfamiliar job posting under their account with applicants accumulating against it).
**Severity:** critical

### SL-11 — Accidental duplicate job postings
**Category:** edge
**Input Scenario:** Recruiter double-submits the post-job form (network lag, double-click) creating two identical job postings.
**Expected Behavior:** No duplicate-prevention is necessarily expected (these could be legitimate near-identical postings) — but the recruiter dashboard must clearly show two separate entries, not merge/miscount them.
**Severity:** low

---

## 3. Candidate Applies — Including New Abuse Patterns

### SL-12 — Concurrent double-apply (race condition)
**Category:** race-condition
**Input Scenario:** Two near-simultaneous `POST /applications/apply` for the same `candidate_id` + `job_posting_id`.
**Expected Behavior:** Exactly one `Applications` row, one set of per-round `Interviews` rows.
**Failure Mode:** Confirmed check-then-insert race in `apply_to_job` (`application_service.py:47-75`, repeated at `89-105`), no unique constraint or transaction isolation. Produces duplicate rows, double-counted in `get_job_stats`.
**Severity:** high

### SL-13 — Multiple applications with slight variation to the same job
**Category:** abuse
**Input Scenario:** Candidate applies to the same job once with no CV, gets `ATS_PENDING`→ likely `ATS_FAIL` (weak profile-only signal). Candidate then re-applies to the *same job* with a different, padded/stuffed CV attached, hoping the second attempt re-triggers a fresh, more favorable ATS run, since `apply_to_job`'s existing-application path (`row` found at line 54) allows `resume_id` to be updated on the existing application.
**Expected Behavior:** Updating the CV on an existing application should either (a) explicitly re-trigger ATS re-evaluation with the new CV, intentionally, as a supported "update and retry" flow, or (b) be blocked once ATS has already run, to prevent rubric-shopping by resubmission.
**Failure Mode:** **Confirmed by code reading**: `apply_to_job` allows `UPDATE Applications SET resume_id = ?` on re-apply (`application_service.py:57-62`) with no check on current `Applications.status` — a candidate already `ATS_FAIL` can swap in a new CV via re-apply, but `run_ats_for_application`'s own cache-check (`status in _ATS_FAILED_STATUSES` → return cached fail) means the *new* CV never actually gets evaluated unless something explicitly re-triggers ATS after the swap. Net effect is confusing either way: either the candidate's CV update is silently ignored (cached fail persists despite a genuinely improved CV) or — if the frontend happens to call `run-ats` again and the cache-check is somehow bypassed — the candidate gets unlimited free re-rolls of the ATS check by resubmitting CVs until one passes, which is a fairness/gaming concern for other candidates.
**Severity:** high

### SL-14 — Job expires exactly today (boundary)
**Category:** edge
**Input Scenario:** Apply to a job whose `expires_at` date equals today's date exactly.
**Expected Behavior:** Accepted (date-only comparison includes the full expiry day), consistent between `/jobs` listing and `apply_to_job` validation (previously fixed to match).
**Severity:** medium

### SL-15 — Stale page apply after expiry
**Category:** edge
**Input Scenario:** Candidate has the Apply dialog open on a job that expires while the dialog sits open (e.g. left the tab open overnight), then submits.
**Expected Behavior:** Backend independently re-validates expiry at submission time regardless of how stale the frontend's view is.
**Severity:** high

### SL-16 — Forged candidate_id in apply request
**Category:** adversarial
**Input Scenario:** Apply with a `candidate_id` that is actually a `recruiter_id` (no real `CandidateProfiles` row), or a syntactically-valid-but-nonexistent UUID.
**Expected Behavior:** Clean validation error; no orphaned `Applications` row created.
**Severity:** medium

### SL-17 — Apply to a non-active job via direct API call
**Category:** adversarial
**Input Scenario:** Bypass the frontend (which only shows active jobs) and `POST /applications/apply` directly against a `draft` or `closed` job's ID.
**Expected Behavior:** Backend independently enforces `status='active'`, rejecting the apply.
**Severity:** medium

### SL-18 — Eligibility check bypassed via direct API manipulation
**Category:** adversarial
**Input Scenario:** Candidate applies, ATS auto-runs and returns `ATS_FAIL`. Candidate then directly calls `POST /interviews/{first_round_interview_id}/generate-questions`, skipping the ATS gate entirely (since the frontend would normally never show the "go to interview" CTA for a failed-ATS application, but the backend endpoint itself takes no `application_id`/ATS-status parameter to check against).
**Expected Behavior:** Rejected — an interview round should not be startable for an application that hasn't passed ATS, regardless of how the request was made.
**Failure Mode:** **Confirmed gap by code reading**: `generate_interview_questions`'s only guard is the interview's own `status` (`Scheduled`/`In Progress`/etc.) — it never checks the *application's* ATS outcome. Since `apply_to_job` pre-creates all per-round `Interviews` rows as `Scheduled` regardless of ATS outcome (rows are created before ATS even runs, per the apply flow), every applicant — including ones who will fail or have already failed ATS — has fully startable interview rows sitting in the DB from the moment they apply. The only thing stopping a failed-ATS candidate from starting round 1 is the frontend not showing them the button. A direct API call bypasses this completely.
**Severity:** critical

### SL-19 — Partial application completion but interview still startable
**Category:** edge
**Input Scenario:** Candidate begins the apply flow, CV upload succeeds and `parse_and_store_cv` completes, but the request is interrupted (network drop) before `apply_to_job`'s final `INSERT INTO Applications` commits — or, alternately, the `Applications` row is created but the per-round `Interviews` row creation loop fails partway for a job with several rounds.
**Expected Behavior:** Atomic outcome: either nothing is created (clean retry) or the application is fully, consistently set up (all expected per-round rows present).
**Failure Mode:** `apply_to_job` does the `Applications` INSERT and the per-round `Interviews` INSERT loop within what's presumably one connection's transaction (confirmed `conn.commit()` once at the end) — *if* that holds, a mid-loop failure should roll back cleanly on `conn.close()` without an explicit commit (needs verification, same open question as `AI-SB-01`). If atomicity does NOT hold (partial commit somehow occurs, e.g. via autocommit misconfiguration), a candidate could end up with an `Applications` row but missing `Interviews` rows for some rounds — meaning those rounds are simply never offered to them, silently, with the candidate never aware a round was skipped due to a system error rather than the round being legitimately `Not Needed`.
**Severity:** high

### SL-20 — Multiple interviews running in parallel for the same candidate
**Category:** abuse / race-condition
**Input Scenario:** Candidate has two different jobs' interview rounds both in `Scheduled` state (normal — they applied to both). They open two browser tabs and start **both** voice/written interviews simultaneously, actively answering both at the same time (e.g. to use one as a "practice run" referencing answers from the other, or simply because nothing stops it).
**Expected Behavior:** Not necessarily forbidden (legitimately, a candidate can be mid-pipeline on multiple jobs) — but the system should not let answering one interview leak context (timer state, question content, scoring) into the other, and resource usage (two simultaneous LLM/STT/TTS sessions for one human) should be sane.
**Failure Mode:** No cross-interview concurrency limit was found anywhere (no "one active interview per candidate at a time" guard). For voice interviews specifically this compounds with `VA-06`/`VA-20` (two simultaneous LiveKit sessions, same human, different rooms) — each is independently a known-untested case; running them genuinely concurrently as a deliberate strategy (not just accidentally) is the adversarial framing worth a dedicated test.
**Severity:** medium

### SL-21 — Score tampering via direct score-answers call (confirmed IDOR, restated as abuse)
**Category:** adversarial
**Input Scenario:** Candidate B calls `POST /interviews/{candidate_A_interview_id}/score-answers` directly with `fetch_from_db=False` and a hand-crafted `answers` payload containing whatever text Candidate B wants graded, attributed to Candidate A's interview.
**Expected Behavior:** Rejected — a candidate can only submit answers for their own interview.
**Failure Mode:** **Confirmed CRITICAL IDOR** (carried forward from prior audit, restated here in the explicit "score tampering" framing the task calls for): zero ownership check exists on this endpoint. This is not just data disclosure — it is a **direct score-manipulation primitive**: Candidate B can overwrite Candidate A's real answers with whatever they choose, then the normal scoring pipeline grades B's chosen text and writes the result onto A's `Interviews` row, potentially triggering A's `_maybe_mark_hired`/`_mark_subsequent_rounds_not_needed` cascades based on entirely fabricated content. A sufficiently informed attacker could engineer another candidate's failure (submit garbage) or — if they also know enough to craft a winning answer — bizarrely "help" a stranger's score for no clear gain, but the failure-injection direction is the serious one: sabotage.
**Severity:** critical

---

## 4. Interview Progression & State Machine

### SL-22 — Candidate jumps stages: applied → hired without any interview
**Category:** adversarial
**Input Scenario:** Candidate applies to a job with 3 configured rounds. Immediately after applying (before ATS even resolves, or immediately after `ATS_PASS`), candidate or an external script directly calls whatever combination of endpoints might flip `Applications.status` to `HIRED` without legitimately passing any round — e.g., probing whether `_maybe_mark_hired`'s "no later active round" check could be tricked by manipulating round `is_active` flags they don't own, or whether any endpoint accepts a direct status write.
**Expected Behavior:** `HIRED` is only reachable via the legitimate path: every active round scored `Pass`, with no other route to that status anywhere in the system.
**Failure Mode:** No endpoint exists that lets a client directly set `Applications.status` (confirmed via the full endpoint inventory — no PATCH/PUT on Applications anywhere) — this specific "skip straight to hired" vector is **not currently exploitable** via a dedicated bypass endpoint. The *real* risk is the already-covered SL-21 (score-tamper a `Pass` onto the *last* round via the IDOR, which then legitimately triggers `_maybe_mark_hired` through the normal cascade) — i.e., stage-jumping is achieved indirectly through the score-tampering vector, not a separate hole. Documented here so "can a candidate jump straight to hired" is explicitly answered (yes, but via SL-21, not a distinct bug).
**Severity:** critical (via SL-21's existing path)

### SL-23 — Fail round 1 of 3; verify cascade and block on direct restart
**Category:** normal + adversarial (two-part case)
**Input Scenario:** (a) Candidate fails round 1 — verify rounds 2-3 flip `Not Needed`, `current_round_id` resolves null. (b) Candidate then directly calls `POST /interviews/{round2_interview_id}/generate-questions`, bypassing the frontend.
**Expected Behavior:** (a) cascade fires correctly. (b) blocked by the `Not Needed` status guard already added to `generate_interview_questions`.
**Failure Mode:** (a) and the guard in (b) were both implemented and unit-tested earlier this engagement (`test_round_cascade.py`) — this case is now a **regression test**, not an open question; included here so it stays in the adversarial suite permanently rather than being assumed safe forever after one fix.
**Severity:** high (regression risk, not an open bug)

### SL-24 — `HIRED` only fires after the genuinely last active round
**Category:** edge
**Input Scenario:** 3-round job, candidate passes round 1 and round 2.
**Expected Behavior:** `Applications.status` stays at whatever it was (not yet `HIRED`) after rounds 1 and 2; only flips after round 3's `Pass`.
**Severity:** high (regression risk — covered by existing unit tests, kept here for end-to-end confirmation)

### SL-25 — Round deactivated mid-pipeline changes the "last round" definition
**Category:** edge
**Input Scenario:** 3-round job. Candidate A is mid-pipeline (passed round 1, round 2 in progress). Recruiter deactivates round 3 (`is_active=0`) before Candidate A reaches it.
**Expected Behavior:** `_maybe_mark_hired`'s "no later active round" check re-evaluates against the now-2-round-effective job — Candidate A should be marked `HIRED` after round 2's `Pass`, not stuck waiting for a round that's no longer active.
**Failure Mode:** Code reading confirms the check is dynamic (queries `is_active=1` at cascade-time, not a cached round count) — should work correctly, but the *reverse* direction is the genuinely risky one: what happens to candidates who **already completed** round 3 before it was deactivated? `get_job_stats`/`get_round_candidates` filter `is_active=1`, meaning those candidates' completed-round-3 data becomes invisible/orphaned in recruiter-facing views even though it's still in the DB. Needs live verification of whether already-`HIRED` status (if they finished before deactivation) persists correctly, vs. candidates who were mid-round-3 when it got deactivated (interview row exists, but the round itself no longer shows up anywhere for the recruiter to review).
**Severity:** medium

### SL-26 — Validator never returns Pass from a forced-fail event type
**Category:** adversarial
**Input Scenario:** Trigger cheating-termination and leave-mid-interview events; inspect `interview_validator.py`'s returned status for both.
**Expected Behavior:** Both always return `Failed`, never `Pass`, regardless of any score value passed in.
**Severity:** high

### SL-27 — Cross-job HIRED leakage
**Category:** edge
**Input Scenario:** Same candidate, two different jobs (two `Applications` rows). Both have their last-round interview scored `Pass` in close succession.
**Expected Behavior:** Each application's `HIRED` status is set independently — Job A's cascade never touches Job B's `Applications` row.
**Failure Mode:** `_maybe_mark_hired`'s `WHERE id = (SELECT application_id FROM Interviews WHERE id = ?)` scoping is per-interview, which is per-application by construction (an `Interviews` row belongs to exactly one `application_id`) — **structurally safe by code reading**, included as a standing regression case given how much cascading logic depends on correct scoping.
**Severity:** low (regression-guard)

---

## 5. Recruiter Visibility / Authorization Boundaries

### SL-28 — Cross-recruiter analytics IDOR (confirmed CRITICAL, carried forward)
**Category:** adversarial
**Input Scenario:** Recruiter A calls `GET /jobs/{recruiter_B_job_id}/stats`, `/rounds/{round_order}/candidates`, `/candidate-panel/{application_id}`, `/jobs/interview-qa/{interview_id}` using IDs belonging to Recruiter B.
**Expected Behavior:** 403/404.
**Failure Mode:** Confirmed — zero ownership filtering on any of these four endpoints/service functions.
**Severity:** critical

### SL-29 — Cross-candidate interview IDOR, including write access (confirmed CRITICAL, carried forward)
**Category:** adversarial
**Input Scenario:** Candidate B accesses/mutates Candidate A's `interview-stages`, `questions`, and `score-answers` using A's IDs.
**Expected Behavior:** 403/404 on read; write blocked entirely.
**Failure Mode:** Confirmed — same root cause, this endpoint set additionally allows mutation (see SL-21).
**Severity:** critical

### SL-30 — `/jobs/mine` returns another recruiter's listings if `recruiter_id` is swapped
**Category:** adversarial
**Input Scenario:** Call `GET /jobs/mine?recruiter_id={other_recruiter_id}`.
**Expected Behavior:** Rejected, or returns nothing, unless the caller genuinely is that recruiter (session-verified).
**Failure Mode:** `list_recruiter_jobs(recruiter_id)` takes the parameter at face value — same root-cause class as SL-28, but on the listing endpoint itself, meaning the *discovery* step (finding what job_ids exist to then attack via SL-28) doesn't even require guessing IDs — a swapped `recruiter_id` here hands over the full target list directly.
**Severity:** critical

### SL-31 — Candidate panel for an orphaned/deleted candidate profile
**Category:** edge
**Input Scenario:** View `get_candidate_panel` for an `application_id` whose `CandidateProfiles`/`Users` row no longer exists (hypothetical data-retention/deletion scenario — no delete endpoint currently exists for these tables either, so this is forward-looking).
**Expected Behavior:** Clean 404, not a 500 from a failed INNER JOIN.
**Severity:** medium

---

## 6. Job Data Integrity & Feed Correctness

### SL-32 — Job posting with missing/null optional metadata still fully visible
**Category:** edge
**Input Scenario:** Post a job with `salary_range: null`, zero `skill_ids`, and the shortest possible valid `description`.
**Expected Behavior:** Job displays correctly in `/jobs` feed with graceful "not specified" handling for missing fields, never a broken card or a 500 from a null-handling gap.
**Failure Mode:** `JobListItem` schema marks `salary_range` as `str | None` (handled), `required_skills` as a list (empty list handled by frontend's existing conditional render) — appears safe by code reading. Included as a standing case since "missing metadata still shows" is explicitly called out as a target scenario — confirms the system correctly does NOT hide incomplete-but-valid listings (that's the right behavior; the wrong behavior would be silently excluding jobs with sparse metadata from the feed, which was not found to happen).
**Severity:** low

### SL-33 — Duplicate/near-duplicate job roles causing incorrect matching
**Category:** edge
**Input Scenario:** `JobRoles` table (signup/job-posting metadata) contains two entries that are effectively the same role with slightly different naming (e.g. "Machine Learning Engineer" and "ML Engineer" as two distinct `job_role_id` rows) — a data-quality scenario, not a code bug, but one the system has no defense against.
**Expected Behavior:** N/A as a "bug" — flagged as a product/data-governance gap: if recruiters can freely create near-duplicate role entries (verify whether `JobRoles` is a fixed seeded list or recruiter-extensible), candidate-side filtering by `job_role_id` would silently miss relevant postings under the "other" near-duplicate role, fragmenting the job feed's effective searchability with no error or warning to either party.
**Severity:** medium (data governance, not a crash risk)

### SL-34 — `applicants_count`/`hired_count` accuracy under the confirmed duplicate-application race
**Category:** adversarial
**Input Scenario:** Combine SL-12's duplicate-application race with `get_job_stats`'s aggregate counts.
**Expected Behavior:** Counts reflect unique humans, not raw row counts.
**Failure Mode:** `total_applicants`/`applicants_count` both do plain `COUNT(*)`/`COUNT(DISTINCT application_id)` against `Applications`/`Interviews` — a duplicate-application race directly inflates these numbers, and since `applicants_count` per round is already known to count every pre-created `Interviews` row regardless of whether the candidate ever reached that round (documented gap from the prior round of testing), this compounds two separate inaccuracies into the same displayed number.
**Severity:** medium

---

## SYSTEM BREAK SCENARIOS (System Logic)

### SL-SB-01 — There is no authentication layer; every "permission" in the system is theater
**Category:** adversarial / system-break
**Input Scenario:** Take literally any endpoint in the system that accepts a `candidate_id`, `recruiter_id`, `application_id`, `interview_id`, or `job_id` as a parameter, and call it with any value the caller chooses — no login token, no session cookie, no API key, nothing beyond knowing or guessing an ID.
**Expected Behavior:** A real system distinguishes "I am candidate X, here is proof" from "I am claiming to be candidate X." This system does not — confirmed by a zero-result grep across the entire backend for any session/token/auth-dependency mechanism.
**Failure Mode:** This is the umbrella finding behind SL-10, SL-18, SL-21, SL-22, SL-28, SL-29, SL-30, and arguably every "abuse"-category case in this file that involves "candidate B does X to candidate A's data" — they are all the same root cause expressed through different endpoints. Patching each endpoint individually (adding an ownership-filter `WHERE` clause here, a status-check there) treats symptoms. The actual fix is architectural: introduce a real session mechanism (JWT issued at signin, validated via a FastAPI dependency on every protected route) so that `candidate_id`/`recruiter_id` are derived **server-side from a verified token**, never trusted as a client-supplied parameter, for any endpoint that performs a sensitive read or any write at all.
**Severity:** critical

### SL-SB-02 — Cascading data corruption from one unguarded race condition compounding through dependent cascades
**Category:** race-condition / system-break
**Input Scenario:** Trigger SL-12 (duplicate application race) for a candidate on a job, such that two `Applications` rows and two full sets of per-round `Interviews` rows exist for what should be one candidate. The candidate then proceeds through interviews normally, but every round-completion event now has **two** `Interviews` rows to consider per round (one per duplicate `Applications` row) — meaning `_mark_subsequent_rounds_not_needed` and `_maybe_mark_hired`, both scoped by `application_id` (correctly, per-application), now run **independently and inconsistently** across the two duplicate applications: one duplicate might fail round 1 and cascade `Not Needed` correctly within itself, while the other duplicate (a completely separate set of `Interviews` rows, also pre-created at the race-condition apply time) is still sitting at `Scheduled` for all rounds, fully startable.
**Expected Behavior:** Should be structurally impossible — one human, one candidacy, one consistent state per job.
**Failure Mode:** The duplicate-application race (already a known gap) doesn't just inflate a count — it creates **two independent, diverging interview state machines for what the recruiter and candidate both believe is one application**. A candidate could fail on one duplicate and still have a fully live, unfailed second duplicate to attempt — the cascade logic added this session is *correct in isolation* but assumes its `application_id` scoping unit is unique per human-per-job, an assumption the apply-race directly violates.
**Severity:** critical

### SL-SB-03 — Silent data loss from non-atomic multi-step writes under partial failure
**Category:** stress / system-break
**Input Scenario:** Any of the multi-step write sequences in this system (apply_to_job's Applications+per-round-Interviews creation, post_job's JobPostings+JobRequiredSkills+InterviewRounds creation, generate_interview_questions's per-question Questions+InterviewQuestions insert loop) experiences a failure on step N of M, after a real DB connection drop, host restart, or out-of-memory kill — not a clean application-level exception, but the process dying mid-transaction.
**Expected Behavior:** Database-level transaction guarantees ensure all-or-nothing regardless of how the failure occurs (clean exception vs. process death).
**Failure Mode:** Atomicity in this codebase appears to rely on pyodbc's connection-level commit/rollback-on-close behavior (no explicit `BEGIN TRANSACTION`/`SAVEPOINT` usage was found anywhere), which protects against clean Python-level exceptions but **not** against the connection itself being killed mid-write by an external process failure — in that scenario, whatever was already flushed to the DB server (even if the client-side commit never completed) may or may not be rolled back depending on SQL Server's own connection-loss transaction handling, which is implementation detail this codebase has not explicitly verified or tested against. Production-realistic trigger: a deploy/restart happening to coincide with an in-flight multi-row write.
**Severity:** high

### SL-SB-04 — Job posting state and interview pipeline diverge permanently with no reconciliation path
**Category:** edge / system-break
**Input Scenario:** A job is posted, candidates apply and progress partway through its interview pipeline, then the recruiter (hypothetically, once such a feature exists — currently absent) needs to edit the round configuration (add/remove/reorder rounds) after candidates are already mid-pipeline against the *original* round configuration.
**Expected Behavior:** Either round-config edits are forbidden once any candidate has started interviewing (simplest safe answer), or there's an explicit migration/reconciliation step for in-flight candidates.
**Failure Mode:** No round-editing endpoint currently exists (confirmed via the endpoint inventory) — this is **not yet exploitable**, but it is a designed-in time bomb: the moment this feature is added (a near-certain future requirement for any real recruiting product), every piece of round-order-dependent cascade logic (`_maybe_mark_hired`'s "no later active round," `_mark_subsequent_rounds_not_needed`'s "round_order > X," `get_interview_stages`'s `current_round_id` resolution) becomes vulnerable to exactly this class of mid-pipeline-reconfiguration inconsistency unless explicitly designed for at the time that feature ships. Flagged now so it's a known constraint on that future feature's design, not a fire to fight after the fact.
**Severity:** high (forward-looking — zero current exploitability, high future risk if unaddressed at design time)
