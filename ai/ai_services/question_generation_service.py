from agents.interview_agent.prompts import (
    GENERATE_QUESTIONS_SYSTEM_PROMPT,
    GENERATE_QUESTIONS_USER_PROMPT,
)
from agents.interview_agent.schemas import (
    CandidateCVRelevance,
    GeneratedQuestions,
    QuestionItem,
    RelevantProject,
    RelevantSkill,
)
from ai_configs.config import get_llm
from ai_services.question_bank_service import InterviewContext


def _format_skills(skills: list[RelevantSkill]) -> str:
    if not skills:
        return "(none)"
    return "\n".join(
        f"- {skill.skill_name} ({skill.proficiency_level}, "
        f"{skill.years_of_experience} yrs)"
        for skill in skills
    )


def _format_projects(projects: list[RelevantProject]) -> str:
    if not projects:
        return "(none)"
    return "\n".join(
        f"- {project.project_name}: {project.description} "
        f"[skills: {', '.join(project.skills_used)}]"
        for project in projects
    )


def _format_questions(questions: list[QuestionItem]) -> str:
    if not questions:
        return "(none)"
    return "\n".join(f"- {question.question_text}" for question in questions)


async def generate_questions(
    example_questions: list[QuestionItem],
    candidate_relevance: CandidateCVRelevance,
    count: int,
    context: InterviewContext,
) -> GeneratedQuestions:
    """generate_questions(): LLM call producing `count` interview questions
    for the given example questions, candidate CV relevance, and interview
    context."""

    structured_llm = get_llm(temperature=0.7).with_structured_output(GeneratedQuestions)

    user_prompt = GENERATE_QUESTIONS_USER_PROMPT.format(
        count=count,
        job_role_title=context.job_role_title,
        job_role_category=context.job_role_category,
        experience_level_name=context.experience_level_name,
        round_type_name=context.round_type_name,
        job_experience_summary=candidate_relevance.job_experience_summary or "(none)",
        relevant_skills=_format_skills(candidate_relevance.relevant_skills),
        relevant_projects=_format_projects(candidate_relevance.relevant_projects),
        example_questions=_format_questions(example_questions),
    )

    return await structured_llm.ainvoke(
        [
            ("system", GENERATE_QUESTIONS_SYSTEM_PROMPT),
            ("user", user_prompt),
        ]
    )
