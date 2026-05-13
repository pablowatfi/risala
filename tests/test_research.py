"""
Research agent tests — mocked web search + LLM-as-judge.

Tavily is mocked for all tests to avoid billing and flakiness.
The judge evaluates whether the LLM summary is a useful briefing given the search results.
"""
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import requires_llm
from tests.fixtures.messages import RECRUITER_EMAIL, NEWSLETTER_EMAIL
from app.agents.research import research_node

pytestmark = [pytest.mark.integration, requires_llm()]

_FAKE_RESULTS = [
    {
        "title": "Meta Platforms — About",
        "url": "https://about.meta.com",
        "content": (
            "Meta Platforms, Inc. builds technologies that help people connect. "
            "Products include Facebook, Instagram, WhatsApp, Messenger, and Quest VR headsets. "
            "Headquartered in Menlo Park, CA with ~70,000 employees worldwide."
        ),
    },
    {
        "title": "Meta Careers — Engineering",
        "url": "https://careers.meta.com/engineering",
        "content": (
            "Meta's engineering teams work on AI, ML, and distributed systems at massive scale. "
            "The Ranking & Recommendations team builds ML systems that serve billions of users daily. "
            "Compensation is highly competitive with significant RSU grants."
        ),
    },
]


def _make_state(msg: dict, needs_research: bool = True) -> dict:
    return {
        "normalized_message": msg,
        "classification": {
            "needs_research": needs_research,
            "priority": "high",
            "category": "meeting",
        },
    }


# ── Deterministic assertions ──────────────────────────────────────────────────

class TestResearchNode:
    async def test_skips_when_no_research_needed(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock) as mock_search:
            result = await research_node(_make_state(NEWSLETTER_EMAIL, needs_research=False))
            mock_search.assert_not_called()
            assert result == {}, "research_node must return empty dict when needs_research is False"

    async def test_returns_research_dict(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_RESULTS):
            result = await research_node(_make_state(RECRUITER_EMAIL))
            assert "research" in result
            assert "summary" in result["research"]
            assert "sources" in result["research"]

    async def test_summary_is_non_empty(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_RESULTS):
            result = await research_node(_make_state(RECRUITER_EMAIL))
            assert len(result["research"]["summary"]) > 50, "Summary should be a meaningful briefing"

    async def test_sources_have_required_fields(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_RESULTS):
            result = await research_node(_make_state(RECRUITER_EMAIL))
            for source in result["research"]["sources"]:
                assert "title" in source, "Source missing 'title'"
                assert "url" in source, "Source missing 'url'"

    async def test_sources_capped_at_five(self):
        many_results = _FAKE_RESULTS * 4  # 8 results
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=many_results):
            result = await research_node(_make_state(RECRUITER_EMAIL))
            assert len(result["research"]["sources"]) <= 5

    async def test_handles_empty_search_results(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=[]):
            result = await research_node(_make_state(RECRUITER_EMAIL))
            assert "research" in result
            assert result["research"]["summary"] == "No relevant research found."
            assert result["research"]["sources"] == []

    async def test_web_search_called_with_focused_query(self):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_RESULTS) as mock_search:
            await research_node(_make_state(RECRUITER_EMAIL))
            mock_search.assert_called_once()
            query_arg = mock_search.call_args[0][0]
            # Query should be a non-trivial, content-driven string (not just the raw sender address)
            assert len(query_arg) > 5, "web_search must be called with a non-empty query"
            assert "@" not in query_arg, (
                "Query should be a human-readable search string, not a raw email address"
            )


# ── LLM-as-judge quality evaluation ──────────────────────────────────────────

class TestResearchJudge:
    async def test_recruiter_research_quality(self, judge):
        with patch("app.agents.research.web_search", new_callable=AsyncMock, return_value=_FAKE_RESULTS):
            result = await research_node(_make_state(RECRUITER_EMAIL))
        summary = result.get("research", {}).get("summary", "")

        verdict = await judge(
            output=summary,
            context=(
                "Input: Email from sarah.johnson@meta.com — Meta recruiter for Senior ML Engineer role.\n"
                "Search results provided:\n"
                "- Meta Platforms: builds Facebook, Instagram, WhatsApp, Quest VR; ~70k employees; Menlo Park HQ.\n"
                "- Meta Careers: Ranking & Recommendations team builds ML systems at massive scale; competitive comp."
            ),
            criteria=(
                "1. Summary must mention Meta as a company (what they do or their scale).\n"
                "2. Summary must be 2-5 sentences — brief but informative enough to be useful.\n"
                "3. Summary should help the user understand who the sender is and whether to respond.\n"
                "4. Summary must be grounded in the search results — no hallucinated details.\n"
                "5. Summary should ideally tie the research back to the email context "
                "(ML/Ranking role, compensation, or scheduling ask).\n"
                "Deduct 5 points if summary is empty, generic, or says 'No relevant research found' "
                "despite having real results."
            ),
        )
        assert verdict.passed, (
            f"Research quality score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )
