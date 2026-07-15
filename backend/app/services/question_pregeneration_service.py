"""Background written-test question pre-generation.

Extracted out of interview_service.py so written_test_tasks.py (the Celery
task that calls pregenerate_interview_questions) can import this module at
top level instead of lazily importing interview_service.py — the two used to
lazily import each other, a genuine circular-dependency risk. This module is
a one-directional consumer of interview_service.py's DB helpers (never the
reverse), so no cycle exists here.
"""
import logging

from app.ai.ai_services.cv_relevance_service import fetch_candidate_cv_relevance
from app.ai.ai_services.question_bank_service import fetch_interview_context
from app.ai.ai_services.question_generation_service import generate_questions
from app.ai.interview_tools.schemas import CandidateCVRelevance
from app.database import db_cursor
from app.services.interview_service import (
    _fetch_existing_questions,
    get_interview_context,
    store_generated_questions,
)
from app.services.pregen_lock import acquire_pregen_lock, release_pregen_lock

logger = logging.getLogger(__name__)


async def pregenerate_interview_questions(interview_id: str) -> bool:
    """Best-effort background pre-generation for a single round — called from the Celery
    task (written_test_tasks.trigger) right after ATS passes (first round) or a prior
    round is scored Pass (next round), via find_next_scheduled_round.

    Skips (returns False, no DB write) when: the round is Oral/Voice — voice rounds are
    driven live by the voice agent, so pre-generating a written question set for one
    would be wasted work; or InterviewQuestions already exist for this interview_id
    (a prior pre-generation run already completed, or the candidate already started
    live via generate_interview_questions — same _fetch_existing_questions check that
    function uses as its own cache-hit gate, so both paths agree on what "already
    generated" means).

    Never touches Interviews.status — that only changes when the candidate actually
    opens the round (generate_interview_questions flips Scheduled -> In Progress),
    so pre-generating here must not make an untouched round look started.
    """
    ctx = get_interview_context(interview_id)
    interview_type = ctx["interview_type"]

    # Substring match — reusing the frontend's convention (InterviewRoom.tsx:
    # .toLowerCase().includes('oral') / .includes('voice')), not the backend's
    # answer_scoring_service.py/interview_validator.py exact-tuple check. That backend
    # check only ever sees an already-normalized "oral"/"written" literal from the
    # frontend; here we're working directly off the raw InterviewRoundTypes.name value
    # (e.g. "Oral Technical"), which the exact-match convention would misclassify.
    lowered = interview_type.lower()
    if "oral" in lowered or "voice" in lowered:
        logger.info("pregenerate: skipping oral/voice round for interview_id=%s (type=%s)", interview_id, interview_type)
        return False

    if not acquire_pregen_lock(interview_id):
        logger.info("pregenerate: interview_id=%s lock already held by a concurrent generation, skipping", interview_id)
        return False

    try:
        with db_cursor() as (conn, cur):
            if _fetch_existing_questions(cur, interview_id):
                logger.info("pregenerate: interview_id=%s already has questions, skipping", interview_id)
                return False
            cur.execute(
                "SELECT experience_level_id FROM CandidateProfiles WHERE id = ?",
                ctx["candidate_id"],
            )
            cp_row = cur.fetchone()
            experience_level_id = int(cp_row[0]) if cp_row and cp_row[0] else 1

        try:
            context = await fetch_interview_context(
                interview_round_type_id=ctx["interview_round_type_id"],
                job_role_id=ctx["job_role_id"],
                experience_level_id=experience_level_id,
            )
            parsed_cv_text = await fetch_candidate_cv_relevance(application_id=ctx["application_id"])
            candidate_relevance = CandidateCVRelevance(
                job_experience_summary=parsed_cv_text,
                relevant_skills=[],
                relevant_projects=[],
            )
            generated = await generate_questions(
                example_questions=[],
                candidate_relevance=candidate_relevance,
                count=10,
                context=context,
            )
        except Exception:
            logger.exception("pregenerate: question generation failed for interview_id=%s", interview_id)
            return False

        new_texts = [q.question_text for q in generated.generated_questions]

        with db_cursor() as (conn, cur):
            store_generated_questions(
                cur, interview_id, new_texts,
                ctx["interview_round_type_id"], ctx["job_role_id"], experience_level_id,
            )
            conn.commit()

        logger.info("pregenerate: stored %d questions for interview_id=%s", len(new_texts), interview_id)
        return True
    finally:
        release_pregen_lock(interview_id)
