from app.database import db_cursor


async def fetch_candidate_cv_relevance(application_id: str) -> str:
    """Return the parsed CV text for the resume attached to the given application.

    Queries Applications for resume_id, then Resumes for parsed_text.
    Returns an empty string if no resume is attached or parsed_text is NULL.
    """
    with db_cursor() as (conn, cur):
        cur.execute(
            "SELECT resume_id FROM Applications WHERE id = ?",
            application_id,
        )
        row = cur.fetchone()
        resume_id = row[0] if row else None

        if not resume_id:
            return ""

        cur.execute(
            "SELECT parsed_text FROM Resumes WHERE id = ?",
            resume_id,
        )
        resume_row = cur.fetchone()
        parsed_text = resume_row[0] if resume_row else None

    return parsed_text or ""
