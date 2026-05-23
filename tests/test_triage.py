"""
Triage agent tests.

Triage is rule-based (no LLM), so these tests are fast unit tests.
They verify that job digest emails from LinkedIn/Wellfound are correctly
categorised, and that regular emails are discarded.
"""
import pytest
from app.agents.ingestion import ingestion_node
from app.agents.triage import triage_node
from tests.fixtures.messages import (
    LINKEDIN_DIGEST,
    WELLFOUND_DIGEST,
    NEWSLETTER_EMAIL,
    EMAIL_WITH_SIGNATURE,
)

pytestmark = pytest.mark.unit


def _make_state(msg: dict) -> dict:
    return {"raw_event": msg, "normalized_message": msg}


# ── Ingestion: job_source detection ──────────────────────────────────────────

class TestJobSourceDetection:
    async def test_linkedin_sender_detected(self):
        result = await ingestion_node({"raw_event": LINKEDIN_DIGEST})
        assert result["normalized_message"]["job_source"] == "linkedin"

    async def test_wellfound_sender_detected(self):
        result = await ingestion_node({"raw_event": WELLFOUND_DIGEST})
        assert result["normalized_message"]["job_source"] == "wellfound"

    async def test_newsletter_has_no_job_source(self):
        result = await ingestion_node({"raw_event": NEWSLETTER_EMAIL})
        assert result["normalized_message"]["job_source"] is None

    async def test_regular_email_has_no_job_source(self):
        result = await ingestion_node({"raw_event": EMAIL_WITH_SIGNATURE})
        assert result["normalized_message"]["job_source"] is None


# ── Triage: category classification ──────────────────────────────────────────

class TestTriageClassification:
    async def test_linkedin_digest_classified_as_job_digest(self):
        ingested = await ingestion_node({"raw_event": LINKEDIN_DIGEST})
        result = await triage_node(ingested)
        assert result["classification"]["category"] == "job_digest"

    async def test_wellfound_digest_classified_as_job_digest(self):
        ingested = await ingestion_node({"raw_event": WELLFOUND_DIGEST})
        result = await triage_node(ingested)
        assert result["classification"]["category"] == "job_digest"

    async def test_newsletter_classified_as_informational(self):
        ingested = await ingestion_node({"raw_event": NEWSLETTER_EMAIL})
        result = await triage_node(ingested)
        assert result["classification"]["category"] == "informational"

    async def test_regular_email_classified_as_informational(self):
        ingested = await ingestion_node({"raw_event": EMAIL_WITH_SIGNATURE})
        result = await triage_node(ingested)
        assert result["classification"]["category"] == "informational"

    async def test_classification_has_category_key(self):
        ingested = await ingestion_node({"raw_event": LINKEDIN_DIGEST})
        result = await triage_node(ingested)
        assert "category" in result["classification"]
