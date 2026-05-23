"""
Unit tests for the ingestion agent — no LLM, no DB, no network.
Tests: normalisation, signature stripping, job source detection, type field.
"""
import pytest
from tests.fixtures.messages import (
    RAW_LINKEDIN_EVENT,
    RAW_WELLFOUND_EVENT,
    RAW_NEWSLETTER_EVENT,
    EMAIL_WITH_SIGNATURE,
)
from app.agents.ingestion import (
    ingestion_node,
    _strip_signature,
    _parse_gmail,
    _detect_job_source,
)

pytestmark = pytest.mark.unit


# ── Signature stripping ───────────────────────────────────────────────────────

class TestSignatureStripping:
    def test_strips_double_dash_delimiter(self):
        body = "Hello, this is the message body.\n\n--\nJohn Smith\njohn@example.com"
        result = _strip_signature(body)
        assert "John Smith" not in result
        assert "Hello, this is the message body." in result

    def test_strips_sent_from_mobile(self):
        body = "Please review this.\nSent from my iPhone"
        result = _strip_signature(body)
        assert "Sent from my iPhone" not in result
        assert "Please review this." in result

    def test_strips_regards(self):
        body = "Can you help?\n\nRegards,\nAlice"
        result = _strip_signature(body)
        assert "Alice" not in result
        assert "Can you help?" in result

    def test_preserves_body_without_signature(self):
        body = "This message has no signature."
        result = _strip_signature(body)
        assert result == body

    def test_strips_signature_from_fixture(self):
        body = EMAIL_WITH_SIGNATURE["body"]
        result = _strip_signature(body)
        assert "John Smith" not in result
        assert "VP Sales" not in result
        assert "partnership" in result.lower()


# ── Job source detection ──────────────────────────────────────────────────────

class TestJobSourceDetection:
    def test_linkedin_domain(self):
        assert _detect_job_source("jobalerts-noreply@linkedin.com") == "linkedin"

    def test_linkedin_subdomain(self):
        assert _detect_job_source("noreply@e.linkedin.com") == "linkedin"

    def test_wellfound_domain(self):
        assert _detect_job_source("notifications@wellfound.com") == "wellfound"

    def test_angel_co_domain(self):
        assert _detect_job_source("jobs@angel.co") == "wellfound"

    def test_regular_sender_returns_none(self):
        assert _detect_job_source("sarah.johnson@meta.com") is None

    def test_newsletter_sender_returns_none(self):
        assert _detect_job_source("newsletter@tldr.tech") is None


# ── Gmail event parsing ───────────────────────────────────────────────────────

class TestGmailParsing:
    def test_normalises_required_fields(self):
        result = _parse_gmail(RAW_LINKEDIN_EVENT)
        for key in ("message_id", "source", "sender", "subject", "body", "thread_id", "received_at"):
            assert key in result, f"Missing field: {key}"

    def test_job_source_set_for_linkedin(self):
        result = _parse_gmail(RAW_LINKEDIN_EVENT)
        assert result["job_source"] == "linkedin"

    def test_job_source_set_for_wellfound(self):
        result = _parse_gmail(RAW_WELLFOUND_EVENT)
        assert result["job_source"] == "wellfound"

    def test_job_source_none_for_newsletter(self):
        result = _parse_gmail(RAW_NEWSLETTER_EVENT)
        assert result["job_source"] is None

    def test_type_job_digest_for_linkedin(self):
        result = _parse_gmail(RAW_LINKEDIN_EVENT)
        assert result["type"] == "job_digest"

    def test_type_email_for_newsletter(self):
        result = _parse_gmail(RAW_NEWSLETTER_EVENT)
        assert result["type"] == "email"

    def test_missing_subject_defaults_to_empty(self):
        event = {**RAW_LINKEDIN_EVENT, "subject": None}
        result = _parse_gmail(event)
        assert result["subject"] == ""


# ── Ingestion node ────────────────────────────────────────────────────────────

class TestIngestionNode:
    async def test_linkedin_event_normalised(self):
        result = await ingestion_node({"raw_event": RAW_LINKEDIN_EVENT})
        assert result["normalized_message"]["source"] == "gmail_personal"
        assert result["normalized_message"]["job_source"] == "linkedin"

    async def test_newsletter_has_no_job_source(self):
        result = await ingestion_node({"raw_event": RAW_NEWSLETTER_EVENT})
        assert result["normalized_message"]["job_source"] is None

    async def test_returns_normalized_message_key(self):
        result = await ingestion_node({"raw_event": RAW_LINKEDIN_EVENT})
        assert "normalized_message" in result

    async def test_normalized_message_has_type_field(self):
        result = await ingestion_node({"raw_event": RAW_LINKEDIN_EVENT})
        assert result["normalized_message"]["type"] == "job_digest"
