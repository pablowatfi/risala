"""
Company research tests — mocked Tavily + LLM-as-judge.

Tests the research functions used by job_pipeline for company research
and cover letter generation.
"""
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import requires_llm
from app.agents.research import generate_cover_letter

pytestmark = [pytest.mark.integration, requires_llm()]

_FAKE_SEARCH_RESULTS = [
    {
        "title": "Stripe Glassdoor",
        "url": "https://glassdoor.com/stripe",
        "content": (
            "Stripe rated 4.2 stars on Glassdoor. Strong engineering culture, "
            "great compensation, fast-paced environment. Some reviews mention "
            "long hours during product launches."
        ),
    },
    {
        "title": "Stripe salaries",
        "url": "https://levels.fyi/stripe",
        "content": "Stripe Senior Engineer base salary ranges from $180k to $220k plus equity.",
    },
    {
        "title": "Stripe r/cscareerquestions",
        "url": "https://reddit.com/r/cscareerquestions/stripe",
        "content": (
            "People on Reddit say Stripe has a high bar in interviews. "
            "The culture is collaborative and the product is beloved by developers."
        ),
    },
]

_FAKE_CV = "Python backend engineer, 8 years experience in distributed systems and payments."


# ── Cover letter generation ───────────────────────────────────────────────────

class TestCoverLetter:
    async def test_cover_letter_is_non_empty(self):
        with patch("app.agents.research.load_cv_text", return_value=_FAKE_CV):
            letter = await generate_cover_letter(
                title="Senior Backend Engineer",
                company="Stripe",
                description="Build payment infrastructure at scale using Python and Go.",
            )
        assert len(letter) > 100, "Cover letter should be a substantial text"

    async def test_cover_letter_mentions_company(self):
        with patch("app.agents.research.load_cv_text", return_value=_FAKE_CV):
            letter = await generate_cover_letter(
                title="Senior Backend Engineer",
                company="Stripe",
                description="Build payment infrastructure at scale.",
            )
        assert "Stripe" in letter, "Cover letter should mention the company name"

    async def test_cover_letter_returns_string(self):
        with patch("app.agents.research.load_cv_text", return_value=_FAKE_CV):
            letter = await generate_cover_letter(
                title="Engineer",
                company="TestCo",
                description="Some job.",
            )
        assert isinstance(letter, str)


# ── LLM-as-judge ─────────────────────────────────────────────────────────────

class TestCoverLetterJudge:
    async def test_cover_letter_quality(self, judge):
        with patch("app.agents.research.load_cv_text", return_value=_FAKE_CV):
            letter = await generate_cover_letter(
                title="Senior Backend Engineer",
                company="Stripe",
                description="Build payment infrastructure at scale using Python and Go.",
            )

        verdict = await judge(
            output=letter,
            context=(
                "Task: write a cover letter for Senior Backend Engineer at Stripe.\n"
                "Candidate: Python backend engineer, 8 years experience in distributed systems and payments."
            ),
            criteria=(
                "1. Letter must mention Stripe by name.\n"
                "2. Letter must be at least 2 substantial paragraphs.\n"
                "3. Letter must reference relevant experience from the candidate's background.\n"
                "4. Letter must NOT include 'Dear Hiring Manager' or a sign-off name placeholder — "
                "those are the user's responsibility.\n"
                "5. Letter should feel genuine and specific, not generic."
            ),
        )
        assert verdict.passed, (
            f"Cover letter quality score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )
