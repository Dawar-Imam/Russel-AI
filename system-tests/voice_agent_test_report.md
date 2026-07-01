# Voice Agent — Test Report (v2)

**Companion to:** `voice_agent_test_cases.md`
**Method:** Static code audit (Grep/Read across `backend/app/ai/voice_agent/`). This layer
requires LiveKit, Deepgram/OpenRouter, and ElevenLabs credentials plus a live WebRTC
session to fully exercise; none were run for this report. The v2 pass went deeper into
`prompts.py` and `agent.py`'s actual control-flow than the v1 report did, which surfaced
several genuine, confirmed bugs (not just gaps) that v1 missed entirely.

Each finding below includes: **Input payload**, **API/module involved**, **Expected vs.
Actual**, **Severity**, **Suggested fix (architectural-level preferred)**.

---

## Severity Summary

| Severity | Confirmed | Not Yet Executed |
|---|---|---|
| CRITICAL | 0 | 5 |
| HIGH | 1 | 10 |
| MEDIUM | 2 | 11 |
| LOW | 0 | 1 |

Three findings were confirmed purely by static code reading this pass (control-flow bugs
and structural gaps that don't require a live model call to verify). The highest-severity
risks in this file (fluency-bias scoring, STT hallucination-as-answer, silent
undetectable cheating, prompt-injection resistance under real adversarial pressure) are
all genuinely **un-confirmable without a live LLM/STT call** — they are listed in the
Not-Yet-Executed table below, not omitted.

---

## CONFIRMED Findings

### F-VA-01 (VA-23) — `/cancel-interview` token silently no-ops, session left in inconsistent state
**Severity:** MEDIUM (demo/test-mode only, but a confirmed live bug)

**Input payload:** Any candidate behavior that causes the interviewer LLM to decide cancellation is warranted (per its own `MISCONDUCT & EARLY-EXIT SIGNALS` judgment), in an environment running with `ENABLE_FAIL_CASES=false`.

**API / module involved:** `backend/app/ai/voice_agent/agent.py:310-323`, `_on_conversation_item`.

**Expected vs. Actual:**
- Expected: the session either never reaches a "say goodbye" state without actually closing, or closes the session regardless of `enable_fail_cases` (only the *Failed-status DB write* should be what's conditionally suppressed, not the disconnect itself).
- Actual: `if cancel_signal and enable_fail_cases: ... elif pass_signal: ...` — when `cancel_signal=True` and `enable_fail_cases=False`, **neither branch executes**. The control token is stripped from speech (candidate hears "I'll end the interview here, thank you for your time" spoken aloud as if it's over), but `disconnected.set()` is never called. The candidate is left live in the room indefinitely, told the interview ended, with the agent now silent and no further questions coming.

**Suggested fix (architectural):** Decouple "should this session end now" from "should this outcome be recorded as a Failure" — these are currently the same boolean gate (`enable_fail_cases`) controlling two unrelated decisions. Split into two independent checks: `disconnected.set()` should fire on cancel_signal unconditionally (the session ending is a UX/flow concern); whether `mark_interview_terminated` actually writes a `Failed` status afterward is the part that should respect `ENABLE_FAIL_CASES`. This is a one-line control-flow fix but flagged as architectural because the underlying pattern — one flag gating two semantically different concerns — is worth auditing for elsewhere in the codebase (the cheating-detection branch at `agent.py:341` has the same `if enable_fail_cases:` gate shape and should be checked for the same coupling).

---

### F-VA-02 (VA-21) — Code-level cheating detection is a small, trivially-evadable English keyword list
**Severity:** HIGH

**Input payload:** Candidate says any cheating admission that doesn't exactly substring-match one of ~13 hardcoded phrases — e.g. *"my friend is helping me right now"*, *"I have the solution on my second screen"*, *"I asked Gemini about this"*, or the same admissions in any non-English language.

**API / module involved:** `backend/app/ai/voice_agent/agent.py:27-42` (`_CHEAT_PHRASES`), `:341-353` (`_on_user_transcript`'s code-level check).

**Expected vs. Actual:**
- Expected: cheating admissions are detected regardless of exact phrasing, since this is meant to be a safety-critical integrity control.
- Actual: `if any(phrase in lowered for phrase in _CHEAT_PHRASES):` is a flat substring match against a fixed list naming only ChatGPT/GPT/Claude by name and a handful of fixed English phrasings. Every example above evades it. The prompt-level cheating-detection instruction (`prompts.py:168-173`) is more robust (semantic, not string-matched) and is the real backstop — but it depends entirely on the LLM correctly classifying the admission in real-time conversation, with no deterministic guarantee.

**Suggested fix (architectural):** Don't try to win this by expanding the keyword list (it will always be a losing game against paraphrase and other languages). The code-level check exists presumably as a fast, deterministic, cheap-to-evaluate safety net underneath the LLM's own judgment — keep it as defense-in-depth, but stop treating its coverage as meaningful, and invest instead in verifying the LLM-level detection's actual real-world recall rate (requires live testing with deliberately paraphrased/multilingual admissions). If a fast, cheap, language-agnostic signal is wanted, consider semantic similarity (embedding-based) matching against a set of "admission" reference phrases instead of exact substrings — still not perfect, but generalizes across phrasing and language far better than substring matching.

---

### F-VA-03 (VA-10) — No-response timer resettable indefinitely by trivial filler speech
**Severity:** MEDIUM

**Input payload:** A single filler word ("uh", "yes", "hmm") spoken roughly every 25 seconds (just under the 30-second default `no_response_timeout_seconds`), for an entire interview, with no substantive answer ever given.

**API / module involved:** `backend/app/ai/voice_agent/agent.py:335` (`_on_user_transcript`), `:159-212` (`_no_response_checker`).

**Expected vs. Actual:**
- Expected: a pattern of non-substantive filler should be treated equivalently to silence for the purposes of the no-response/cancellation counter, or final grading should be the only backstop (acceptable, but should be a deliberate design choice, not an oversight).
- Actual: `last_user_response_time[0] = time.time()` resets unconditionally on any final transcript with no minimum-content/length check, so the no-response timeout — and therefore `cancel_on_no_response` — can never trigger as long as filler speech continues. The candidate cannot pass this way (final grading will still score near-zero on empty content), but they can consume the **entire** interview duration without early cancellation, which is a scheduling/resource-abuse vector and produces a confusing transcript for recruiter review.

**Suggested fix (architectural):** This is a legitimate design question, not just a bug: decide explicitly whether "no-response timeout" should mean "no audio at all" (current, narrow) or "no *substantive* response" (broader, requires either a cheap heuristic like minimum word count, or routing through the same LLM judgment already used for the 6-strikes cancel logic). Recommend the latter — fold "filler-only, no real answer" into the *existing* 6-strikes-on-poor-performance tracking the system prompt already implements, rather than adding a second, separate detection mechanism. The system already has the right judgment mechanism (the LLM's main-question tracking); the no-response timer is solving a narrower problem (true silence/disconnection) and shouldn't be expected to also catch this case.

---

## NOT YET EXECUTED — Requires Live LiveKit/Deepgram/Whisper/ElevenLabs Session

Every multi-intent, audio-quality, timing, and concurrency case in the test file requires
an actual voice session (real or scripted via LiveKit's testing SDK) to verify. Grouped
by what's needed to close them out.

| ID | Severity | What to run |
|---|---|---|
| VA-01–VA-06 | high/medium/critical | Scripted conversational turns through a real session: contradictory single-sentence answers, hint-echoing, direct "reveal the answer" requests, fake-confusion-for-rephrase loops, direct system-override injection phrasing, verbatim answer replay across unrelated questions |
| VA-07, VA-08 | high, medium | Forced mid-sentence disconnect; deliberate barge-in/overlap timing |
| VA-09 | low | Baseline silence-handling confirmation |
| VA-11, VA-12, VA-13 | medium, high, high | Rapid/unbroken long monologue; background noise injection at varying SNR; deliberate near-silence to probe Whisper/Deepgram hallucination — **VA-13 is the highest-value case to run first**, since `whisper_stt.py:167` hardcodes `confidence=1.0` regardless of actual model confidence, meaning the system currently has zero signal to distinguish a real transcription from a hallucinated one even if one wanted to add a confidence-threshold filter later |
| VA-14, VA-15 | high, high | Accented speech; genuine Urdu+English code-switched speech (stated target use case — high product priority to verify, not just a theoretical edge case) |
| VA-16, VA-17 | critical, medium | **Run first**: fluent-buzzword-dense-but-meaningless answer through the real `grade_candidate_answers` call and inspect the actual returned score; minimal one-word answers across several phrasings of yes/no-shaped questions |
| VA-18 | high | Deliberate filibuster monologue consuming the full interview duration on one question |
| VA-19 | medium | Repeated "skip"/"pass" responses — verify these count toward the 6-strikes threshold the same as wrong answers |
| VA-20, VA-24 | high, high | Two-device concurrent room join; rapid double-submit of `voice-interview` start |
| VA-25 | critical | Simulate agent-join failure after token issuance — check for indefinite stuck session |
| VA-26 | medium | Long-lived abandoned `status-stream` SSE connections at scale |
| VA-27 | high | Concurrent `save_voice_answers_bulk` calls with the documented duplicate-question-emission pattern |

**Priority recommendation, in order:** VA-16 (fluency-bias scoring — highest plausible
product-trust impact, cheapest to test, just needs one real scoring call), VA-13
(hallucination-on-silence — directly enables low-effort cheating-by-silence), VA-25
(stuck-session-no-recovery — directly impacts real candidates' interview completion
rate), VA-05 (direct injection — best-defended on paper, worth confirming the defense
actually holds under a real model call rather than just reading the prompt).
