"""
End-to-end pipeline tests — full LangGraph execution with mocked Telegram + Tavily.

Verifies routing logic, that job digest emails go through the full pipeline,
and that non-job emails exit early.
Telegram and web search are always mocked.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import requires_llm
from tests.fixtures.messages import (
    RAW_LINKEDIN_EVENT,
    RAW_WELLFOUND_EVENT,
    RAW_NEWSLETTER_EVENT,
)
from app.graph.graph import build_graph

pytestmark = [pytest.mark.integration, requires_llm()]

_FAKE_SEARCH = [
    {
        "title": "Stripe Glassdoor",
        "url": "https://glassdoor.com/stripe",
        "content": "Stripe rated 4.2 stars. Great engineering culture, competitive pay.",
    }
]


@pytest.fixture
def graph():
    return build_graph()


@pytest.fixture(autouse=True)
def mock_telegram():
    with patch("app.agents.telegram_notify.send_alert", new_callable=AsyncMock):
        with patch("app.agents.telegram_notify.send_message", new_callable=AsyncMock):
            yield


@pytest.fixture(autouse=True)
def mock_search():
    with patch("app.agents.job_pipeline.web_search", new_callable=AsyncMock, return_value=_FAKE_SEARCH):
        yield


@pytest.fixture(autouse=True)
def mock_cv():
    with patch("app.agents.research.load_cv_text", return_value="Python backend engineer, 8 years experience."):
        yield


# ── Routing correctness ───────────────────────────────────────────────────────

class TestPipelineRouting:
    async def test_linkedin_event_completes(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        assert "classification" in result
        assert result["classification"]["category"] == "job_digest"

    async def test_wellfound_event_completes(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_WELLFOUND_EVENT})
        assert result["classification"]["category"] == "job_digest"

    async def test_newsletter_exits_early(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_NEWSLETTER_EVENT})
        assert result["classification"]["category"] == "informational"
        # Job pipeline fields should not be populated
        assert not result.get("scored_jobs")

    async def test_job_digest_produces_extracted_jobs(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        assert "extracted_jobs" in result
        assert isinstance(result["extracted_jobs"], list)

    async def test_job_digest_produces_scored_jobs(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        assert "scored_jobs" in result
        assert isinstance(result["scored_jobs"], list)

    async def test_scored_jobs_have_match_tag(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        for job in result.get("scored_jobs", []):
            assert job.get("match_tag") in ("low", "medium", "high"), (
                f"Job missing valid match_tag: {job}"
            )


# ── Filter correctness ────────────────────────────────────────────────────────

class TestLocationFilter:
    async def test_linkedin_argentina_jobs_pass_filter(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        # At least one Argentina job should survive the filter
        filtered = result.get("filtered_jobs", [])
        assert len(filtered) >= 1, "At least one Argentina-based job should pass the LinkedIn filter"

    async def test_wellfound_remote_jobs_pass_filter(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_WELLFOUND_EVENT})
        filtered = result.get("filtered_jobs", [])
        assert len(filtered) >= 1, "At least one full-remote job should pass the Wellfound filter"


# ── State correctness ─────────────────────────────────────────────────────────

class TestPipelineState:
    async def test_normalized_message_preserved(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        msg = result["normalized_message"]
        assert msg["source"] == "gmail_personal"
        assert msg["job_source"] == "linkedin"

    async def test_extracted_jobs_are_dicts(self, graph):
        result = await graph.ainvoke({"raw_event": RAW_LINKEDIN_EVENT})
        for job in result.get("extracted_jobs", []):
            assert isinstance(job, dict)
            assert "title" in job
            assert "company" in job
