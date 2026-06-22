import io
import re

from pypdf import PdfReader


def _extract_bio(text: str) -> str | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    section_keywords = {"summary", "profile", "about", "objective", "overview", "introduction"}
    for i, line in enumerate(lines):
        if line.lower().rstrip(":").rstrip() in section_keywords and i + 1 < len(lines):
            bio_lines = lines[i + 1 : i + 6]
            bio = " ".join(bio_lines)
            if bio:
                return bio[:1000]
    # Fallback: first line longer than 50 chars (skip short header/name lines)
    long_lines = [ln for ln in lines if len(ln) > 50]
    return long_lines[0][:500] if long_lines else None


def _extract_linkedin(text: str) -> str | None:
    match = re.search(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
    if match:
        return f"https://www.{match.group(0)}"
    return None


def _extract_location(text: str) -> str | None:
    match = re.search(
        r'(?:location|address|city)[:\s]+([A-Za-z ,]{3,50})',
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()[:100]
    return None


def parse_pdf_cv(file_content: bytes) -> dict[str, str | None]:
    try:
        reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception:
        return {"bio": None, "linkedin_url": None, "current_location": None}

    return {
        "bio": _extract_bio(text),
        "linkedin_url": _extract_linkedin(text),
        "current_location": _extract_location(text),
    }
