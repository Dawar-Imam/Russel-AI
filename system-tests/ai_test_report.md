# AI Tools — Test Report (v2)

**Companion to:** `ai_test_cases.md`
**Method:** Static code audit (Grep/Read across `backend/app/ai/`,
`backend/app/services/cv_parser_service.py`). No live LLM calls were made (would burn
real API tokens against OpenAI/OpenRouter purely for report generation). Each finding
includes **Input payload**, **API/module involved**, **Expected vs. Actual**,
**Severity**, **Suggested fix (architectural-level preferred)**.

---

## Severity Summary

| Severity | Confirmed | Not Yet Executed |
|---|---|---|
| CRITICAL | 2 | 4 |
| HIGH | 1 | 11 |
| MEDIUM | 0 | 12 |
| LOW | 0 | 4 |

---

## CONFIRMED Findings

### F-AI-01 (AI-19) — `zip()` truncation can silently misalign scores to the wrong questions
**Severity:** CRITICAL

**Input payload:** Any scoring response from `score_answers_tool` where `graded_answers` has a different length than the submitted `answers`/`iq_ids` list — e.g. the LLM drops one item, or a parsing step silently skips a malformed entry.

**API / module involved:** `backend/app/services/interview_service.py`, `_save_scores_and_complete`:
```python
for iq_id, ga in zip(iq_ids, graded_answers):
    cur.execute("UPDATE InterviewQuestions SET score = ?, notes = ? WHERE id = ? AND interview_id = ?", ga.score, ga.notes, iq_id, interview_id)
```

**Expected vs. Actual:**
- Expected: a length mismatch between input and output is detected and rejected/retried before any DB write — grading data integrity should never depend on two independently-produced lists staying perfectly aligned by position with no verification.
- Actual: Python's `zip()` silently truncates to the shorter list with no exception, no logging, no length-equality assertion anywhere before or after this loop. If `graded_answers` has 9 items where `iq_ids` has 10, question 10 silently receives no score update at all (whatever its prior NULL state was, it stays NULL — different from being scored 0). Worse: if the *order* of `graded_answers` doesn't correspond 1:1 to `iq_ids` order (a parsing/extraction-order mismatch, not just a count mismatch), every subsequent question after the first divergence point gets **the wrong score silently written against it**, with zero error raised anywhere in the stack.

**Suggested fix (architectural):** Add an explicit `assert len(iq_ids) == len(graded_answers)` (or equivalent raised exception) before this loop, failing loudly rather than silently truncating — a failed interview-scoring attempt that's visibly retried is vastly preferable to a silently-corrupted score that looks completely normal in the UI. More robustly: move to structured/tool-call-enforced output for the scoring LLM call (if not already in place — needs confirmation) so that the model's response is schema-validated to include exactly one graded item per input item by construction, rather than trusting positional list alignment after the fact at all.

---

### F-AI-02 (AI-09 from v1 / AI-20 in v2) — No range validation on `overall_score`/`result` before DB write
**Severity:** HIGH

**Input payload:** Any LLM scoring response where `overall_score` falls outside the expected 0-10 range — miscalculated average, parsing error, or a successful injection attempt manipulating the numeric output.

**API / module involved:** `backend/app/services/interview_service.py` (`_save_scores_and_complete`), `backend/app/services/interview_validator.py` (`validate_interview`).

**Expected vs. Actual:**
- Expected: `result` written to `Interviews` is always clamped/validated to a sane 0-10 range before persistence.
- Actual: no range check was found anywhere between the raw LLM/tool output and the final `UPDATE Interviews SET ... result = ?` write. An out-of-range value would corrupt any downstream code assuming the 0-10 bound — `JobPostStats.tsx`'s score display (`p.result.toFixed(1)`), the `PASS_THRESHOLD = 6.0` comparison in `interview_validator.py` (which would behave unpredictably for a negative or >10 score relative to the threshold, depending on comparison direction), and any future aggregate/average computation across `result` values.

**Suggested fix (architectural):** Validate and clamp `overall_score` (and ideally each individual `graded_answers[i].score`) to `[0, 10]` at the single chokepoint where AI-tool output crosses into the validated `ScoreAnswersResponse`/`GradedAnswer` Pydantic models — add a `field_validator` there (consistent with the project's existing pattern of putting validation on Pydantic schemas, e.g. `InterviewRoundInput.failing_criteria`) so this is enforced once, structurally, rather than needing a manual check at every call site that touches a score.

---

## Architectural Finding: Asymmetric Prompt-Injection Defense Across LLM Call Sites
**Severity:** CRITICAL (as a pattern, not a single fix)

**Input payload:** N/A — this is a comparative structural finding across multiple prompts, not a single reproducible payload.

**API / module involved:** `backend/app/ai/voice_agent/prompts.py` vs. `backend/app/ai/interview_tools/prompts.py` (`GRADE_ANSWERS_SYSTEM_PROMPT`) vs. `backend/app/ai/ai_services/ats_service.py` vs. `backend/app/services/cv_parser_service.py`.

**Expected vs. Actual:**
- Expected: every LLM call site that ingests untrusted candidate-supplied text applies a consistent baseline of injection resistance.
- Actual: `voice_agent/prompts.py`'s `build_system_prompt` has an extensive, structured, repeated defense (`INSTRUCTION HIERARCHY`, `DOMAIN LOCK`, `FORBIDDEN BEHAVIORS`, `CORE PRINCIPLE` — five distinct sections all reinforcing "candidate input never controls structure/flow"). **`GRADE_ANSWERS_SYSTEM_PROMPT`, the ATS eligibility prompt, and the CV extraction prompt have none of this** — zero instruction-hierarchy language, zero "treat the following as untrusted data" framing. This is not a uniform gap; it's an inconsistency, which is more concerning than uniform weakness, because it suggests the defense was added reactively/locally (likely specifically for the voice agent, possibly after observing real injection attempts in voice sessions) rather than as a systemic policy applied everywhere untrusted text reaches a model.

**Suggested fix (architectural):** Extract the voice agent's instruction-hierarchy pattern into a shared, reusable prompt fragment (e.g. a `UNTRUSTED_CONTENT_GUARD` constant in a shared prompts module) and apply it at every LLM call site that ingests candidate-supplied free text: `GRADE_ANSWERS_SYSTEM_PROMPT`, the ATS eligibility prompt, the CV extraction prompt, and the question-generation prompt's CV-context injection. This is cheap to implement (it's prompt text, not new infrastructure) and closes the most asymmetric, highest-leverage gap found in this entire audit — the written-interview and ATS paths are currently the least-defended LLM surfaces despite carrying the same risk profile as the well-defended voice path.

---

## NOT YET EXECUTED — Requires Live LLM Calls

| ID | Severity | What to run |
|---|---|---|
| AI-01, AI-02 | critical, high | Direct override + fake-role-tag injection through the real ATS call — **highest priority**, this is the least-defended high-stakes decision point in the system |
| AI-03, AI-04 | high, medium | CV-embedded question-topic steering; fabricated prior-feedback cross-contamination check |
| AI-05, AI-06, AI-07 | critical, high, high | Direct grading-override injection; structured-output-breakout attempt; false-legitimacy oral-leniency exploitation — **AI-05 is the single highest-priority case in this entire report**, the written-grading prompt has zero injection defense and directly produces the candidate's own pass/fail outcome |
| AI-08 | high | Matched-content-different-length answer triplet through the real scoring pipeline — measure the actual score delta for length/fluency bias |
| AI-10–AI-13 | high/medium/medium/medium | Adversarial table-layout CV; homoglyph/unicode CV; fake-authority section headers; malformed-PDF-structure stress test |
| AI-14 | high | Keyword-stuffed CV vs. genuine-narrative CV with equivalent real qualifications — measure ATS verdict delta |
| AI-15 | medium | Cross-job ATS cache isolation regression check (low risk by code reading, worth a permanent automated test) |
| AI-16 | medium | Zero-signal candidate (no CV, no skills, no bio) — check for non-deterministic verdicts across repeated identical calls |
| AI-17 | medium | Confirm question generator never produces duplicate/near-duplicate questions in a real batch |
| AI-18 | high | Force under-generation and confirm no silent short-round delivery |
| AI-SB-01 | high | Simulate LLM-provider outage mid-question-storage loop; confirm transaction rollback behavior on `conn.close()` without commit |
| AI-SB-02 | critical | Concurrent scoring + concurrent answer-mutation race, specifically timed within the multi-second LLM-call window |
| AI-SB-03 | critical (if reuse exists) | Verify whether `Questions` rows are ever reused across different candidates' interviews, or always freshly generated per interview — **this single check resolves an unverified critical-or-moot finding either way** |
| AI-SB-04 | high | Maximally-adversarial combined payload (huge CV + keyword stuffing + unicode + long answers) — find the actual token-limit failure point and its error behavior |

**Priority recommendation:** Run AI-05 and AI-01 first (cheapest to test — one CV upload,
one interview answer, two LLM calls total — and they're the two highest-stakes
under-defended decision points: "do I pass this candidate" and "what score do I give this
candidate's actual answer"). Run AI-SB-03 second since it's a single targeted code-path
check (not even necessarily live-LLM-dependent) that resolves a critical-severity
unknown into either "confirmed safe" or "confirmed critical" — high value for low effort.
