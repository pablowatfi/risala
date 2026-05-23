"""
Gmail integration tests.

Unit (no network): header decoding, body extraction, raw message parsing.
Integration (mark.gmail): requires token files + real Gmail API.
"""
import base64
import email
import pytest
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tests.conftest import requires_gmail
from app.integrations.gmail import (
    _decode_header_value,
    _extract_body,
    _parse_gmail_message,
)


# ── Header decoding ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestHeaderDecoding:
    def test_plain_ascii(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_empty_header(self):
        assert _decode_header_value("") == ""

    def test_email_with_display_name(self):
        result = _decode_header_value("John Smith <john@example.com>")
        assert "John Smith" in result
        assert "john@example.com" in result

    def test_utf8_b64_encoded_header(self):
        # "Héllo" encoded as UTF-8 base64 RFC2047
        encoded = "=?utf-8?b?SOlsbG8=?="
        result = _decode_header_value(encoded)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_does_not_crash_on_malformed(self):
        result = _decode_header_value("=?unknown?q?bad_encoding?=")
        assert isinstance(result, str)


# ── Body extraction ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBodyExtraction:
    @staticmethod
    def _simple_email(text: str) -> email.message.Message:
        return email.message_from_bytes(
            f"From: test@example.com\r\nSubject: Test\r\n\r\n{text}".encode()
        )

    @staticmethod
    def _multipart_email(plain: str) -> email.message.Message:
        msg = MIMEMultipart("alternative")
        msg["From"] = "test@example.com"
        msg["Subject"] = "Multipart"
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(f"<html><body><b>{plain}</b></body></html>", "html"))
        return email.message_from_bytes(msg.as_bytes())

    def test_extracts_plain_text(self):
        result = _extract_body(self._simple_email("Hello, world!"))
        assert "Hello, world!" in result

    def test_extracts_plain_from_multipart(self):
        result = _extract_body(self._multipart_email("Plain text content"))
        assert "Plain text content" in result

    def test_returns_string_for_empty_body(self):
        msg = email.message_from_bytes(b"From: test@example.com\r\n\r\n")
        result = _extract_body(msg)
        assert isinstance(result, str)

    def test_returns_string_type(self):
        result = _extract_body(self._simple_email("any content"))
        assert isinstance(result, str)


# ── Raw message parsing ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestGmailMessageParsing:
    @staticmethod
    def _raw_message(subject: str, sender: str, body: str, msg_id: str = "msg-001") -> dict:
        raw_bytes = (
            f"From: {sender}\r\n"
            f"Subject: {subject}\r\n"
            f"Date: Tue, 13 May 2026 09:00:00 +0000\r\n"
            f"\r\n{body}"
        ).encode("utf-8")
        return {
            "id": msg_id,
            "threadId": f"thread-{msg_id}",
            "raw": base64.urlsafe_b64encode(raw_bytes).decode(),
        }

    def test_required_fields_present(self):
        raw = self._raw_message("Subject", "alice@example.com", "Body")
        result = _parse_gmail_message(raw, "gmail_work")
        for key in ("message_id", "source", "sender", "subject", "body", "thread_id", "received_at"):
            assert key in result, f"Missing key: {key}"

    def test_source_propagated(self):
        raw = self._raw_message("Test", "alice@example.com", "Body")
        assert _parse_gmail_message(raw, "gmail_personal")["source"] == "gmail_personal"
        assert _parse_gmail_message(raw, "gmail_work")["source"] == "gmail_work"

    def test_message_id_matches(self):
        raw = self._raw_message("Test", "alice@example.com", "Body", msg_id="abc-123")
        assert _parse_gmail_message(raw, "gmail_work")["message_id"] == "abc-123"

    def test_thread_id_matches(self):
        raw = self._raw_message("Test", "alice@example.com", "Body", msg_id="x1")
        assert _parse_gmail_message(raw, "gmail_work")["thread_id"] == "thread-x1"

    def test_body_content_preserved(self):
        raw = self._raw_message("Test", "alice@example.com", "Hello from the test suite")
        assert "Hello from the test suite" in _parse_gmail_message(raw, "gmail_work")["body"]

    def test_subject_decoded(self):
        raw = self._raw_message("Important Update", "alice@example.com", "Body")
        assert _parse_gmail_message(raw, "gmail_work")["subject"] == "Important Update"

    def test_received_at_is_valid_iso(self):
        raw = self._raw_message("Test", "alice@example.com", "Body")
        received_at = _parse_gmail_message(raw, "gmail_work")["received_at"]
        # Should parse without error
        dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        assert dt is not None


# ── Gmail API connectivity (requires token files) ─────────────────────────────

@pytest.mark.gmail
class TestGmailConnectivity:
    @requires_gmail("gmail_work")
    def test_work_account_credentials_valid(self):
        from app.integrations.gmail import _load_or_refresh_creds
        from app.config import settings
        from google.auth.exceptions import RefreshError
        try:
            creds = _load_or_refresh_creds(settings.GMAIL_WORK_TOKEN_FILE)
        except RefreshError:
            pytest.skip("gmail_work token expired — re-run OAuth flow")
        assert creds is not None
        assert creds.valid

    @requires_gmail("gmail_personal")
    def test_personal_account_credentials_valid(self):
        from app.integrations.gmail import _load_or_refresh_creds
        from app.config import settings
        from google.auth.exceptions import RefreshError
        try:
            creds = _load_or_refresh_creds(settings.GMAIL_PERSONAL_TOKEN_FILE)
        except RefreshError:
            pytest.skip("gmail_personal token expired — re-run OAuth flow")
        assert creds is not None
        assert creds.valid

    @requires_gmail("gmail_work")
    def test_work_account_api_reachable(self):
        from app.integrations.gmail import _load_or_refresh_creds
        from app.config import settings
        from google.auth.exceptions import RefreshError
        from googleapiclient.discovery import build
        try:
            creds = _load_or_refresh_creds(settings.GMAIL_WORK_TOKEN_FILE)
        except RefreshError:
            pytest.skip("gmail_work token expired — re-run OAuth flow")
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        assert "emailAddress" in profile
