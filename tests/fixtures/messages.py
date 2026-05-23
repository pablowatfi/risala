"""
Dummy message payloads for all tests.
"""

# ── LinkedIn job digest ───────────────────────────────────────────────────────
# Expected: job_source="linkedin", category="job_digest"

LINKEDIN_DIGEST = {
    "source": "gmail_personal",
    "message_id": "msg-linkedin-001",
    "thread_id": "thread-linkedin-001",
    "sender": "jobalerts-noreply@linkedin.com",
    "subject": "3 new jobs for Senior Backend Engineer",
    "body": (
        "Jobs recommended for you\n\n"
        "Senior Backend Engineer\n"
        "Mercado Libre · Buenos Aires, Argentina · Remote\n"
        "Apply: https://www.linkedin.com/jobs/view/3900001\n\n"
        "Staff Software Engineer\n"
        "Ualá · Buenos Aires, Argentina\n"
        "Apply: https://www.linkedin.com/jobs/view/3900002\n\n"
        "Backend Engineer\n"
        "Accenture · United States · On-site\n"
        "Apply: https://www.linkedin.com/jobs/view/3900003\n\n"
        "Unsubscribe from job alerts\n"
    ),
    "received_at": "2026-05-20T09:00:00Z",
}

# ── Wellfound job digest ──────────────────────────────────────────────────────
# Expected: job_source="wellfound", category="job_digest"

WELLFOUND_DIGEST = {
    "source": "gmail_personal",
    "message_id": "msg-wellfound-001",
    "thread_id": "thread-wellfound-001",
    "sender": "notifications@wellfound.com",
    "subject": "New jobs matching your profile",
    "body": (
        "Top jobs for you\n\n"
        "Stripe\n"
        "Senior Backend Engineer\n"
        "Full Remote · Series B · $150k-$200k\n"
        "Python, Go, distributed systems\n"
        "Apply: https://wellfound.com/jobs/stripe-senior-backend\n\n"
        "Vercel\n"
        "Staff Engineer\n"
        "Fully Remote · Series C\n"
        "Node.js, TypeScript, cloud infrastructure\n"
        "Apply: https://wellfound.com/jobs/vercel-staff-eng\n\n"
        "Brex\n"
        "Backend Engineer\n"
        "On-site San Francisco · Relocation required\n"
        "Apply: https://wellfound.com/jobs/brex-backend\n\n"
        "Unsubscribe\n"
    ),
    "received_at": "2026-05-20T10:00:00Z",
}

# ── Non-job email (informational) ─────────────────────────────────────────────
# Expected: job_source=None, category="informational"

NEWSLETTER_EMAIL = {
    "source": "gmail_personal",
    "message_id": "msg-newsletter-001",
    "thread_id": "thread-newsletter-001",
    "sender": "newsletter@tldr.tech",
    "subject": "TLDR Tech — May 20 2026",
    "body": (
        "TLDR Tech Newsletter — May 20 2026\n\n"
        "1. OpenAI releases new reasoning model\n"
        "2. Google announces Gemini 3 at I/O\n\n"
        "Unsubscribe | Manage preferences\n"
    ),
    "received_at": "2026-05-20T07:00:00Z",
}

# ── Email with signature to be stripped ──────────────────────────────────────

EMAIL_WITH_SIGNATURE = {
    "source": "gmail_work",
    "message_id": "msg-sig-001",
    "thread_id": "thread-sig-001",
    "sender": "partner@vendor.com",
    "subject": "Partnership proposal",
    "body": (
        "Hi Pablo,\n\n"
        "We'd love to explore a partnership.\n\n"
        "--\n"
        "John Smith\n"
        "VP Sales, Vendor Corp\n"
    ),
    "received_at": "2026-05-20T13:00:00Z",
}

# ── Raw Gmail webhook payload shapes ─────────────────────────────────────────

RAW_LINKEDIN_EVENT = {**LINKEDIN_DIGEST}
RAW_WELLFOUND_EVENT = {**WELLFOUND_DIGEST}
RAW_NEWSLETTER_EVENT = {**NEWSLETTER_EMAIL}
