import asyncio

from app.ai.interview_tools.schemas import AnswerItem
from app.ai.interview_tools.state import AgentState
from app.ai.interview_tools.tools import generate_questions_tool, score_answers_tool

# ---------------------------------------------------------------------------
# Shared test state (IDs must exist in the DB seed data)
# ---------------------------------------------------------------------------
BASE_STATE: AgentState = {
    "candidate_id": "b0000001-0000-0000-0000-000000000001",
    "job_posting_id": "e0000001-0000-0000-0000-000000000001",
    "application_id": "a0000001-0000-0001-0000-000000000001",
    "interview_round_type_id": 1,
    "job_role_id": 1,
    "experience_level_id": 2,
    "count": 3,
}


# ---------------------------------------------------------------------------
# Test 1 — generate_questions_tool
# ---------------------------------------------------------------------------
async def test_generate_questions() -> list[str]:
    print("=" * 60)
    print("TEST 1: generate_questions_tool")
    print("=" * 60)

    state: AgentState = dict(BASE_STATE)
    result = await generate_questions_tool(state)

    if result["status"] != "success":
        print("FAIL — generate_questions_tool returned status != success")
        return []

    questions = result["questions"]
    print(f"PASS — generated {len(questions)} question(s):")
    for i, q in enumerate(questions, 1):
        print(f"  Q{i}: {q.question_text}")
    print()
    return [q.question_text for q in questions]


# ---------------------------------------------------------------------------
# Test 2 — score_answers_tool
# ---------------------------------------------------------------------------
async def test_score_answers(questions: list[str]) -> None:
    print("=" * 60)
    print("TEST 2: score_answers_tool")
    print("=" * 60)

    # Use provided questions or fall back to hardcoded ones
    if not questions:
        questions = [
            "Tell me about your experience with Python.",
            "How do you handle tight deadlines?",
            "Describe a time you resolved a production incident.",
        ]

    hardcoded_answers = [
        "I have been writing Python professionally for three years, mainly "
        "for backend APIs and data pipelines using FastAPI and SQLAlchemy.",
        "I break the work into smaller tasks, communicate blockers early, "
        "and prioritise ruthlessly so the most critical items ship first.",
        "I added extra logging, identified a slow DB query via the logs, "
        "added an index, and deployed a hotfix within two hours.",
    ]

    answers = [
        AnswerItem(question_text=q, candidate_answer=a)
        for q, a in zip(questions, hardcoded_answers)
    ]

    state: AgentState = {**BASE_STATE, "answers": answers}
    result = await score_answers_tool(state)

    if result["status"] != "success":
        print("FAIL — score_answers_tool returned status != success")
        return

    print(f"PASS — scored {result['total_graded']} answer(s):")
    for g in result["graded_answers"]:
        print(f"  [{g.score}/10] {g.question_text[:60]}...")
        print(f"         {g.notes}")
    print(f"\n  Overall score: {result['overall_score']:.2f} / 10")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    print("\n=== Russel.AI — Interview Tools Test Suite ===\n")
    questions = await test_generate_questions()
    await test_score_answers(questions)
    print("=== All tests complete ===\n")


if __name__ == "__main__":
    asyncio.run(main())
