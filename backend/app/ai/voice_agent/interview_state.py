"""
Shared in-process state for voice interview conclude signals.

Both agent.py (writer) and room_connection.py (reader) import from here
to avoid a circular import between those two modules.
"""

_conclude_results: dict[str, dict] = {}


def store_conclude_result(interview_id: str, passed: bool, reason: str) -> None:
    """Called by the agent's conclude_interview tool when the interview ends."""
    _conclude_results[interview_id] = {"passed": passed, "reason": reason}


def pop_conclude_result(interview_id: str) -> dict | None:
    """Consume and return the conclude result for this interview, or None if not stored."""
    return _conclude_results.pop(interview_id, None)
