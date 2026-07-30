"""
Interview fail-case validation layer.

Called before every DB commit that finalises an interview result.
Returns a fully normalised ValidationResult — the caller just writes it.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXIT_EVENTS = frozenset({
    "user_exit", "logout", "tab_switch", "refresh", "navigation",
})

# Written-test pass rule: candidate needs this many questions scored >= 7/10 to
# pass, independent of the continuous overall_score threshold used for oral
# rounds. Only applied when interview_type is not oral/voice and correct_count
# was supplied by the caller.
WRITTEN_TEST_MIN_CORRECT = 10

# Interviews.status values (lowercased) that represent a scored, final outcome
# for this specific round. Deliberately narrower than TERMINAL_ROUND_STATUSES
# below — "not needed" rounds were never scored, so they don't count as
# "already decided" for idempotency purposes.
SCORED_STATUSES = ("pass", "failed")

# Interviews.status values (lowercased) after which a round must never be
# regenerated or rescored — either it was scored (SCORED_STATUSES), it was
# cascade-skipped because an earlier round in the same application failed, or it
# was deleted (a scheduled round whose candidate never joined within the join
# window — see interview_service.mark_interview_deleted_no_show).
TERMINAL_ROUND_STATUSES = ("pass", "failed", "not needed", "deleted")

_FEEDBACK_WRITTEN_LEAVE = "User left the interview, interview automatically closed."
_FEEDBACK_ORAL_LEAVE = "User switched tabs and cheated, thus interview closed."
_FEEDBACK_CHEATING = (
    "Candidate admitted to cheating during the voice interview. Interview terminated."
)
_FEEDBACK_SCORE_FAIL = "Interview score fell below the required threshold."
_FEEDBACK_SCORE_PASS = "Interview completed successfully."


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ValidationInput:
    """All information the validator needs; no DB access inside the validator."""
    # What triggered this validation
    # Values: timer_end | submit | user_exit | logout | tab_switch | refresh |
    #         navigation | cheating | normal_completion
    event_type: str

    computed_score: float        # AI-computed score 0–10; 0 when not yet scored
    failing_criteria: float      # Pass threshold (e.g. 6.0)
    enable_fail_cases: bool

    current_status: str          # Scheduled | In Progress | Pass | Failed
    interview_type: str = "written"   # written | oral
    cheating_detected: bool = False
    correct_count: int | None = None  # written tests only: # of questions scored >= 7/10


def _determine_pass_status(inp: "ValidationInput", score: float, logs: list[str]) -> str:
    """Written tests (non-oral) with a supplied correct_count pass on count of
    correct answers (>= WRITTEN_TEST_MIN_CORRECT); everything else (oral rounds,
    or written calls that didn't supply correct_count) falls back to the
    continuous score-vs-failing_criteria threshold."""
    is_written = inp.interview_type.lower() not in ("oral", "voice")
    if is_written and inp.correct_count is not None:
        status = "Pass" if inp.correct_count >= WRITTEN_TEST_MIN_CORRECT else "Failed"
        logs.append(
            f"written test: correct_count={inp.correct_count} "
            f"required>={WRITTEN_TEST_MIN_CORRECT} → {status}"
        )
        return status
    status = "Pass" if score >= inp.failing_criteria else "Failed"
    logs.append(f"score={score:.1f} criteria={inp.failing_criteria} → {status}")
    return status


@dataclass
class ValidationResult:
    final_score: float
    final_status: str        # "Pass" | "Failed"
    final_feedback: str
    applied_rule: str        # machine-readable reason
    is_override: bool        # True when forced score/status overrides AI result
    validation_logs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_interview(inp: ValidationInput) -> ValidationResult:
    """
    Single source of truth for interview result correctness.

    Rules are applied in priority order:
      1. Idempotency guard (already terminal)
      2. fail_cases disabled → score-only determination
      3. Cheating → forced Failed / 0
      4. Exit event → forced Failed / 0
      5. Timer-end / submit → score vs criteria
      6. Consistency guard
    """
    logs: list[str] = []

    # ── 1. Idempotency ─────────────────────────────────────────────────────
    if inp.current_status.lower() in SCORED_STATUSES:
        logs.append(f"idempotency: already '{inp.current_status}' — no change")
        return ValidationResult(
            final_score=inp.computed_score,
            final_status="Pass" if inp.current_status.lower() == "pass" else "Failed",
            final_feedback="",
            applied_rule="idempotency_guard",
            is_override=False,
            validation_logs=logs,
        )

    # ── 2. fail_cases DISABLED ──────────────────────────────────────────────
    if not inp.enable_fail_cases:
        logs.append("fail_cases=false: exit/cheat overrides suppressed")
        if inp.event_type in _EXIT_EVENTS:
            logs.append(f"exit event '{inp.event_type}' ignored in test mode")
        if inp.cheating_detected:
            logs.append("cheating flag suppressed in test mode")

        score = max(0.0, inp.computed_score)
        status = _determine_pass_status(inp, score, logs)
        feedback = _FEEDBACK_SCORE_PASS if status == "Pass" else _FEEDBACK_SCORE_FAIL
        return ValidationResult(
            final_score=score,
            final_status=status,
            final_feedback=feedback,
            applied_rule="score_only_test_mode",
            is_override=False,
            validation_logs=logs,
        )

    # ── fail_cases ENABLED ─────────────────────────────────────────────────

    # ── 3. Cheating — highest priority override ─────────────────────────────
    if inp.cheating_detected or inp.event_type == "cheating":
        logs.append("cheating detected → forced Failed, score=0")
        return ValidationResult(
            final_score=0.0,
            final_status="Failed",
            final_feedback=_FEEDBACK_CHEATING,
            applied_rule="cheating_termination",
            is_override=True,
            validation_logs=logs,
        )

    # ── 4. Exit events — override with score=0 ──────────────────────────────
    if inp.event_type in _EXIT_EVENTS:
        feedback = (
            _FEEDBACK_ORAL_LEAVE
            if inp.interview_type.lower() in ("oral", "voice")
            else _FEEDBACK_WRITTEN_LEAVE
        )
        logs.append(f"exit event '{inp.event_type}' → forced Failed, score=0")
        return ValidationResult(
            final_score=0.0,
            final_status="Failed",
            final_feedback=feedback,
            applied_rule=f"exit_event:{inp.event_type}",
            is_override=True,
            validation_logs=logs,
        )

    # ── 5. Normal completion / timer / submit — score-based ─────────────────
    score = max(0.0, inp.computed_score)
    status = _determine_pass_status(inp, score, logs)
    feedback = _FEEDBACK_SCORE_PASS if status == "Pass" else _FEEDBACK_SCORE_FAIL

    # ── 6. Consistency guard ────────────────────────────────────────────────
    # Pass + score=0 is logically invalid unless it was an intended override
    # (overrides return early above, so this catches accidental bad AI output)
    if status == "Pass" and score == 0.0:
        logs.append("consistency: Pass + score=0 → corrected to Failed")
        status = "Failed"
        feedback = _FEEDBACK_SCORE_FAIL

    # High-score + Failed would only happen if criteria > score intentionally — allow it.

    return ValidationResult(
        final_score=score,
        final_status=status,
        final_feedback=feedback,
        applied_rule="score_vs_criteria",
        is_override=False,
        validation_logs=logs,
    )
