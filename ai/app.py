import asyncio

from agents.interview_agent.schemas import AnswerItem
from agents.interview_agent.tools import score_answers_tool
from graph.graph import interview_graph
from graph.state import AgentState


async def main() -> None:
    print("=== Russel.AI Interview Agent CLI ===")
    print("-- generate_questions_tool --\n")

    state: AgentState = {
        "candidate_id": "b0000001-0000-0000-0000-000000000001",
        "job_posting_id": "e0000001-0000-0000-0000-000000000001",
        "application_id": "a0000001-0000-0001-0000-000000000001",
        "interview_round_type_id": 1,
        "job_role_id": 1,
        "experience_level_id": 2,
        "count": 2,
    }

    state = await interview_graph.ainvoke(state)

    if state.get("status") != "success":
        print("\ngenerate_questions_tool failed.")
        return

    questions = state["questions"]
    print(f"\nGenerated {state['total_questions']} questions.\n")

    answers: list[AnswerItem] = []
    for i, question in enumerate(questions, start=1):
        print(f"Q{i}: {question.question_text}")
        candidate_answer = input("Your answer: ").strip()
        answers.append(
            AnswerItem(question_text=question.question_text, candidate_answer=candidate_answer)
        )
        print()

    print("-- score_answers_tool --\n")
    state["answers"] = answers
    # score_answers_tool has no incoming graph edge yet (see graph/graph.py),
    # so it's invoked directly as a node function for now.
    state.update(await score_answers_tool(state))

    if state.get("status") != "success":
        print("score_answers_tool failed.")
        return

    for graded in state["graded_answers"]:
        # print(f"Q: {graded.question_text}")
        # print(f"A: {graded.candidate_answer}")
        print(f"Score: {graded.score}/10")
        print(f"Notes: {graded.notes}\n")

    print(f"Overall score: {state['overall_score']:.2f}")
    print(f"Total graded: {state['total_graded']}")


if __name__ == "__main__":
    asyncio.run(main())
