"""
End-to-end pipeline tests — full LangGraph execution with mocked Telegram + Tavily.

Verifies routing logic, state threading, and that no nodes crash on real inputs.
Telegram send_alert is always mocked — we never send real notifications in tests.
"""
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import requires_llm
from tests.fixtures.messages import (
    RAW_GMAIL_EVENT,
    RAW_SLACK_EVENT,
    NEWSLETTER_EMAIL,
    URGENT_EMAIL,
    TASK_EMAIL,
)
from app.graph.graph import build_graph

pytestmark = [pytest.mark.integration, requires_llm()]

_FAKE_SEARCH = [
    {
        "title": "Meta Platforms",
        "url": "https://about.meta.com",
        "content": "Meta builds social technology including Facebook, Instagram, and WhatsApp.",
    }
]


@pytest.fixture
def graph():
    return build_graph()


@pytest.fixture(autouse=True)
def mock_telegram():
    """Block all real Telegram API calls for every pipeline test."""
    with patch("app.agents.telegram_notify.send_alert", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_calendar():
    """Block real Google Calendar API calls — tokens don't have calendar scope in tests."""
    with patch("app.agents.meeting.get_free_slots", new_callable=AsyncMock, return_value=[]):
        yield


@pytest.fixture
def mock_search():
    with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_SEARCH) as mock:
        yield mock


# ── Routing correctness ───────────────────────────────────────────────────────

class TestPipelineRouting:
    async def test_gmail_event_completes(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        assert "classification" in result
        assert "normalized_message" in result

    async def test_slack_event_completes(self, graph):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=[]):
            result = await graph.ainvoke({"raw_event": RAW_SLACK_EVENT})
        assert result["normalized_message"]["source"] == "slack"

    async def test_newsletter_classified_as_low_priority(self, graph):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=[]):
            result = await graph.ainvoke({"raw_event": NEWSLETTER_EMAIL})
        assert result["classification"]["priority"] == "low", (
            f"Newsletter must be low priority through the full pipeline, "
            f"got: {result['classification']['priority']}"
        )

    async def test_urgent_email_triggers_telegram(self, graph, mock_telegram):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=[]):
            result = await graph.ainvoke({"raw_event": URGENT_EMAIL})
        assert result["classification"]["priority"] == "high"
        mock_telegram.assert_called_once(), "High-priority urgent email must trigger Telegram alert"

    async def test_recruiter_runs_research_when_flagged(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        clf = result["classification"]
        if clf.get("needs_research"):
            assert "research" in result, "research key must be in state when needs_research=True"
            mock_search.assert_called_once()

    async def test_task_email_produces_tasks(self, graph):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=[]):
            result = await graph.ainvoke({"raw_event": TASK_EMAIL})
        assert "tasks" in result
        assert isinstance(result["tasks"], list)


# ── State threading ───────────────────────────────────────────────────────────

class TestPipelineState:
    async def test_db_message_id_set_after_triage(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        assert result.get("db_message_id") is not None, (
            "triage_node must set db_message_id and it must survive through the full pipeline"
        )

    async def test_classification_has_all_required_keys(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        clf = result["classification"]
        for key in ("is_work_related", "priority", "category", "needs_research", "needs_draft", "reasoning"):
            assert key in clf, f"Missing classification key after full pipeline: {key}"

    async def test_normalized_message_preserved(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        msg = result["normalized_message"]
        assert msg["source"] == "gmail_work"
        assert msg["sender"] == "sarah.johnson@meta.com"

    async def test_draft_present_when_needed(self, graph, mock_search):
        result = await graph.ainvoke({"raw_event": RAW_GMAIL_EVENT})
        if result["classification"].get("needs_draft"):
            assert result.get("draft"), "draft must be populated when needs_draft=True"
            assert len(result["draft"]) > 10
