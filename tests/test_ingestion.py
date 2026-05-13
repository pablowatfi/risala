"""
Unit tests for the ingestion agent — no LLM, no DB, no network.
Tests: normalisation, signature stripping, Gmail/Slack parsing.
"""
import pytest
from tests.fixtures.messages import (
    RAW_GMAIL_EVENT,
    RAW_SLACK_EVENT,
    EMAIL_WITH_SIGNATURE,
)
from app.agents.ingestion import (
    ingestion_node,
    _strip_signature,
    _parse_gmail,
    _parse_slack,
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


# ── Gmail event parsing ───────────────────────────────────────────────────────

class TestGmailParsing:
    def test_normalises_required_fields(self):
        result = _parse_gmail(RAW_GMAIL_EVENT)
        assert result["message_id"] == "msg-recruiter-001"
        assert result["source"] == "gmail_work"
        assert result["sender"] == "sarah.johnson@meta.com"
        assert result["subject"] == "Senior ML Engineer opportunity at Meta — Ranking team"
        assert result["thread_id"] == "thread-recruiter-001"
        assert result["received_at"] == "2026-05-13T09:15:00Z"
        assert len(result["body"]) > 0

    def test_body_present(self):
        result = _parse_gmail(RAW_GMAIL_EVENT)
        assert "Meta" in result["body"]

    def test_missing_subject_defaults_to_empty(self):
        event = {**RAW_GMAIL_EVENT, "subject": None}
        result = _parse_gmail(event)
        assert result["subject"] == ""

    def test_output_shape(self):
        result = _parse_gmail(RAW_GMAIL_EVENT)
        required_keys = {"message_id", "source", "sender", "subject", "body", "thread_id", "received_at"}
        assert required_keys.issubset(result.keys())


# ── Slack event parsing ───────────────────────────────────────────────────────

class TestSlackParsing:
    def test_normalises_required_fields(self):
        result = _parse_slack(RAW_SLACK_EVENT)
        assert result["source"] == "slack"
        assert result["sender"] == "alice"
        assert "PR" in result["body"]
        assert result["message_id"].startswith("slack_")

    def test_output_shape(self):
        result = _parse_slack(RAW_SLACK_EVENT)
        required_keys = {"message_id", "source", "sender", "subject", "body", "thread_id", "received_at"}
        assert required_keys.issubset(result.keys())

    def test_subject_is_empty_for_slack(self):
        result = _parse_slack(RAW_SLACK_EVENT)
        assert result["subject"] == ""


# ── Ingestion node routing ────────────────────────────────────────────────────

class TestIngestionNode:
    async def test_routes_gmail_event(self):
        state = {"raw_event": RAW_GMAIL_EVENT}
        result = await ingestion_node(state)
        assert result["normalized_message"]["source"] == "gmail_work"

    async def test_routes_slack_event(self):
        state = {"raw_event": RAW_SLACK_EVENT}
        result = await ingestion_node(state)
        assert result["normalized_message"]["source"] == "slack"

    async def test_returns_normalized_message_key(self):
        state = {"raw_event": RAW_GMAIL_EVENT}
        result = await ingestion_node(state)
        assert "normalized_message" in result

    async def test_normalized_message_has_all_fields(self):
        state = {"raw_event": RAW_GMAIL_EVENT}
        result = await ingestion_node(state)
        msg = result["normalized_message"]
        for key in ("message_id", "source", "sender", "subject", "body", "thread_id", "received_at"):
            assert key in msg, f"Missing field: {key}"
