import io
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from app.database import get_connection

_UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads" / "resumes"
_SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".tiff"}

logger = logging.getLogger(__name__)


def _pypdf_to_text(file_content: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception:
        return ""


def _docx_to_text(file_content: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_content))
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception:
        return ""


def _llamaparse_to_markdown(file_content: bytes, file_ext: str = ".pdf") -> str:
    """Parse CV file to plain text. Uses LlamaParse when available; falls back per file type."""
    ext = file_ext.lower()
    api_key = os.environ.get("LLAMA_CLOUD_API_KEY", "")

    if not api_key:
        if ext == ".pdf":
            return _pypdf_to_text(file_content)
        if ext in (".docx", ".doc"):
            return _docx_to_text(file_content)
        # images and other formats need LlamaParse — no local fallback
        logger.warning("CV parser: no LLAMA_CLOUD_API_KEY set; cannot parse %s file", ext)
        return ""

    tmp_path: str | None = None
    try:
        from llama_parse import LlamaParse

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(file_content)
            tmp_path = f.name

        parser = LlamaParse(api_key=api_key, result_type="markdown")
        documents = parser.load_data(tmp_path)
        return "\n\n".join(doc.text for doc in documents)
    except Exception:
        logger.warning("CV parser: LlamaParse failed for %s, falling back to local parser", ext)
        if ext == ".pdf":
            return _pypdf_to_text(file_content)
        if ext in (".docx", ".doc"):
            return _docx_to_text(file_content)
        return ""
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _llm_extract(md_text: str, available_skills: list[dict]) -> dict:
    empty: dict = {
        "bio": None,
        "linkedin_url": None,
        "current_location": None,
        "total_experience_years": None,
        "skills": [],
    }

    if not md_text.strip():
        return empty

    try:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=api_key)

        skill_names = [s["name"] for s in available_skills]

        prompt = f"""You are a CV/resume parser. Extract structured information from the CV text below.

CV:
{md_text[:8000]}

Available skills (return only names that exactly match this list — no others):
{json.dumps(skill_names)}

Return a JSON object with these fields:
- bio: professional summary string (max 500 chars) or null
- linkedin_url: full LinkedIn profile URL or null
- current_location: city and country string or null
- total_experience_years: total years of professional experience as a number or null
- skills: array of objects, each containing:
  - name: must exactly match one entry in the available skills list above
  - proficiency_level: one of "Beginner", "Intermediate", "Advanced", "Expert"
  - years_of_experience: integer (0 if unknown)

Return ONLY the JSON object, no markdown fences, no explanation."""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
    except Exception:
        return empty

    skill_name_to_id: dict[str, int] = {s["name"].lower(): s["id"] for s in available_skills}
    matched_skills: list[dict] = []
    for skill in parsed.get("skills", []):
        name_lower = str(skill.get("name", "")).lower()
        if name_lower in skill_name_to_id:
            matched_skills.append({
                "skill_id": skill_name_to_id[name_lower],
                "proficiency_level": skill.get("proficiency_level", "Intermediate"),
                "years_of_experience": max(0, int(skill.get("years_of_experience") or 0)),
            })

    return {
        "bio": str(parsed["bio"])[:500] if parsed.get("bio") else None,
        "linkedin_url": str(parsed["linkedin_url"]) if parsed.get("linkedin_url") else None,
        "current_location": str(parsed["current_location"])[:100] if parsed.get("current_location") else None,
        "total_experience_years": (
            float(parsed["total_experience_years"])
            if parsed.get("total_experience_years") is not None
            else None
        ),
        "skills": matched_skills,
    }


def parse_and_store_cv(
    file_content: bytes,
    file_name: str | None,
    candidate_id: str,
) -> dict:
    """Full CV pipeline: save file → LlamaParse → LLM extract → store in Resumes table.

    Returns:
        {
            "resume_id": str,
            "file_url": str,
            "parsed_text": str,
            "bio": str | None,
            "linkedin_url": str | None,
            "current_location": str | None,
            "total_experience_years": float | None,
            "skills": [{"skill_id": int, "proficiency_level": str, "years_of_experience": int}],
        }
    """
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file_name).suffix.lower() if file_name else ".pdf"
    if ext not in _SUPPORTED_EXTS:
        ext = ".pdf"
    stored_name = f"{uuid.uuid4()}{ext}"
    (_UPLOADS_DIR / stored_name).write_bytes(file_content)
    file_url = f"uploads/resumes/{stored_name}"

    parsed_text = _llamaparse_to_markdown(file_content, ext)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM SkillSets WHERE is_active = 1")
        available_skills = [{"id": int(row[0]), "name": str(row[1])} for row in cur.fetchall()]
    finally:
        conn.close()

    structured = _llm_extract(parsed_text, available_skills)

    resume_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Resumes (id, candidate_id, file_url, file_name, parsed_text, uploaded_at)
            VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
            """,
            resume_id,
            candidate_id,
            file_url,
            file_name or stored_name,
            parsed_text or None,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "resume_id": resume_id,
        "file_url": file_url,
        "parsed_text": parsed_text,
        **structured,
    }
