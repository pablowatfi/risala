"""
Company research utility — used by job_pipeline and by the cover_letter Telegram handler.
CV documents are loaded once at startup and cached for the process lifetime.
"""
import json
from pathlib import Path

from app.config import settings
from app.integrations.websearch import web_search
from app.llm import get_llm

_cv_cache: str | None = None


def load_cv_text() -> str:
    """Return cached CV text; loads from disk on first call."""
    global _cv_cache
    if _cv_cache is not None:
        return _cv_cache

    parts: list[str] = []

    pdf_dir = Path(settings.CV_PDF_DIR)
    if pdf_dir.exists():
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            try:
                import pypdf
                reader = pypdf.PdfReader(str(pdf_path))
                parts.append("\n".join(page.extract_text() or "" for page in reader.pages))
            except Exception:
                pass

    jobs_dir = Path(settings.CV_JOBS_DIR)
    if jobs_dir.exists():
        for docx_path in sorted(jobs_dir.glob("*.docx")):
            try:
                import docx
                doc = docx.Document(str(docx_path))
                parts.append("\n".join(p.text for p in doc.paragraphs))
            except Exception:
                pass

    _cv_cache = "\n\n---\n\n".join(parts)
    return _cv_cache


_COVER_LETTER_PROMPT = """Write a concise, professional cover letter for this job application.

Job:
Title: {title}
Company: {company}
Description: {description}

Candidate's CV and Experience:
{cv_text}

Guidelines:
- 3-4 paragraphs, direct and genuine
- Highlight the most relevant experience for this specific role
- Do NOT include date, address header, or sign-off name placeholder
- This is a draft only — it will never be sent automatically"""


async def generate_cover_letter(title: str, company: str, description: str) -> str:
    cv_text = load_cv_text()
    llm = get_llm("smart")
    response = await llm.ainvoke(
        _COVER_LETTER_PROMPT.format(
            title=title,
            company=company,
            description=(description or "")[:1000],
            cv_text=cv_text[:3000],
        )
    )
    return response.content
