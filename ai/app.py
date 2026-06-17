import asyncio

from agents.interview_agent.agent import assign_scores, generate_questions


async def main() -> None:
    print("=== Russel.AI Interview Agent CLI ===\n")

    questions = await generate_questions(
        candidate_id="b0000001-0000-0000-0000-000000000001",
        job_posting_id="e0000001-0000-0000-0000-000000000001",
        application_id="a0000001-0000-0001-0000-000000000001",
        interview_round_type_id=1,
        job_role_id=1,
        experience_level_id=2,
        count=2,
    )

    print(f"Generated {len(questions)} questions.\n")

    answers: list[str] = []
    for i, q in enumerate(questions, start=1):
        print(f"Q{i}: {q}")
        answers.append(input("Your answer: ").strip())
        print()

    result = await assign_scores(questions, answers)

    print("-- Results --\n")
    for graded in result.graded_answers:
        print(f"Score: {graded.score}/10")
        print(f"Notes: {graded.notes}\n")

    print(f"Overall score: {result.overall_score:.2f}")
    print(f"Total graded:  {result.total_graded}")


if __name__ == "__main__":
    asyncio.run(main())
