import asyncio

from app.ai.ai_services.answer_scoring_service import grade_candidate_answers
from app.ai.ai_services.cv_relevance_service import fetch_candidate_cv_relevance
from app.ai.ai_services.question_bank_service import fetch_interview_context
from app.ai.ai_services.question_generation_service import generate_questions
from app.ai.interview_tools.schemas import AnswerItem, CandidateCVRelevance

# ---------------------------------------------------------------------------
# Shared test IDs (must exist in the DB seed data)
# ---------------------------------------------------------------------------
CANDIDATE_ID = "b0000001-0000-0000-0000-000000000001"
JOB_POSTING_ID = "e0000001-0000-0000-0000-000000000001"
APPLICATION_ID = "a0000001-0000-0001-0000-000000000001"
INTERVIEW_ROUND_TYPE_ID = 1
JOB_ROLE_ID = 1
EXPERIENCE_LEVEL_ID = 2
COUNT = 3


# ---------------------------------------------------------------------------
# Test 1 — generate_questions
# ---------------------------------------------------------------------------
async def test_generate_questions() -> list[str]:
    print("=" * 60)
    print("TEST 1: generate_questions")
    print("=" * 60)

    context = await fetch_interview_context(
        interview_round_type_id=INTERVIEW_ROUND_TYPE_ID,
        job_role_id=JOB_ROLE_ID,
        experience_level_id=EXPERIENCE_LEVEL_ID,
    )
    parsed_cv_text = await fetch_candidate_cv_relevance(application_id=APPLICATION_ID)
    candidate_relevance = CandidateCVRelevance(
        job_experience_summary=parsed_cv_text,
        relevant_skills=[],
        relevant_projects=[],
    )
    generated = await generate_questions(
        example_questions=[],
        candidate_relevance=candidate_relevance,
        count=COUNT,
        context=context,
    )

    questions = generated.generated_questions
    print(f"PASS — generated {len(questions)} question(s):")
    for i, q in enumerate(questions, 1):
        print(f"  Q{i}: {q.question_text}")
    print()
    return [q.question_text for q in questions]


# ---------------------------------------------------------------------------
# Test 2 — grade_candidate_answers
# ---------------------------------------------------------------------------
async def test_score_answers(questions: list[str]) -> None:
    print("=" * 60)
    print("TEST 2: grade_candidate_answers")
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

    graded = await grade_candidate_answers(answers, interview_type="written")

    print(f"PASS — scored {graded.total_graded} answer(s):")
    for g in graded.graded_answers:
        print(f"  [{g.score}/10] {g.question_text[:60]}...")
        print(f"         {g.notes}")
    print(f"\n  Overall score: {graded.overall_score:.2f} / 10")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    print("\n=== Russel.AI — Interview AI Services Test Suite ===\n")
    questions = await test_generate_questions()
    await test_score_answers(questions)
    print("=== All tests complete ===\n")


if __name__ == "__main__":
    asyncio.run(main())
