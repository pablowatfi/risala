"""
Dummy message payloads for all tests.
Each fixture represents a realistic, well-defined scenario with a known expected outcome.
"""

# ── 1. Recruiter email ────────────────────────────────────────────────────────
# Expected: priority=high, category=meeting, needs_research=True, needs_draft=True

RECRUITER_EMAIL = {
    "source": "gmail_work",
    "message_id": "msg-recruiter-001",
    "thread_id": "thread-recruiter-001",
    "sender": "sarah.johnson@meta.com",
    "subject": "Senior ML Engineer opportunity at Meta — Ranking team",
    "body": (
        "Hi Pablo,\n\n"
        "I hope this message finds you well! I came across your profile on LinkedIn and was "
        "very impressed with your background in machine learning and large-scale systems.\n\n"
        "We have an exciting Senior ML Engineer role on our Ranking & Recommendations team at Meta. "
        "The role involves building recommendation systems that serve billions of users daily.\n\n"
        "Compensation: $280k-$350k total comp (base + RSU + bonus).\n\n"
        "I'd love to schedule a 30-minute introductory call this week. "
        "Would Tuesday May 19th at 2pm PT or Thursday May 21st at 4pm PT work for you?\n\n"
        "Please let me know and I'll send a calendar invite.\n\n"
        "Best regards,\n"
        "Sarah Johnson\n"
        "Technical Recruiter, Meta\n"
        "sarah.johnson@meta.com\n"
    ),
    "received_at": "2026-05-13T09:15:00Z",
}

# ── 2. Task email with deadlines ──────────────────────────────────────────────
# Expected: priority=high, category=task, needs_draft=False (informational internally),
#           tasks=[submit report by May 16, schedule 1:1 by May 22, review deployment by May 20]

TASK_EMAIL = {
    "source": "gmail_work",
    "message_id": "msg-task-001",
    "thread_id": "thread-task-001",
    "sender": "david.chen@company.com",
    "subject": "Q2 Review — Action items assigned to you",
    "body": (
        "Hi Pablo,\n\n"
        "Following up on yesterday's all-hands. Here are the action items assigned to you:\n\n"
        "1. Submit the quarterly metrics report by Friday May 16th EOD\n"
        "2. Schedule a 1:1 onboarding session with the new hire (Alex Rivera) by May 22nd\n"
        "3. Review and approve the new CI/CD deployment process document — due May 20th\n\n"
        "These are blocking the Q2 planning cycle so please prioritise them.\n\n"
        "Thanks,\nDavid Chen\nEngineering Manager\n"
    ),
    "received_at": "2026-05-13T10:00:00Z",
}

# ── 3. Newsletter / informational ─────────────────────────────────────────────
# Expected: priority=low, category=informational, needs_research=False, needs_draft=False

NEWSLETTER_EMAIL = {
    "source": "gmail_personal",
    "message_id": "msg-newsletter-001",
    "thread_id": "thread-newsletter-001",
    "sender": "newsletter@tldr.tech",
    "subject": "TLDR Tech — May 13 2026",
    "body": (
        "TLDR Tech Newsletter — May 13 2026\n\n"
        "1. OpenAI releases new reasoning model\n"
        "2. Google announces Gemini 3 at I/O\n"
        "3. Meta open-sources LLaMA 5\n"
        "4. EU passes new AI regulation framework\n\n"
        "Read more at tldr.tech\n\n"
        "Unsubscribe | Manage preferences\n"
    ),
    "received_at": "2026-05-13T07:00:00Z",
}

# ── 4. Urgent deadline email ──────────────────────────────────────────────────
# Expected: priority=high, category=urgent, needs_draft=True

URGENT_EMAIL = {
    "source": "gmail_work",
    "message_id": "msg-urgent-001",
    "thread_id": "thread-urgent-001",
    "sender": "cto@company.com",
    "subject": "URGENT: Production outage — need your help NOW",
    "body": (
        "Pablo,\n\n"
        "We have a Sev-1 production outage affecting 40% of users. "
        "The ML ranking service is returning 500s.\n\n"
        "Need you online immediately. Can you join the war room call?\n"
        "Zoom link: zoom.us/j/999999\n\n"
        "— James (CTO)\n"
    ),
    "received_at": "2026-05-13T14:30:00Z",
}

# ── 5. Slack message (casual) ─────────────────────────────────────────────────
# Expected: priority=medium, category=task, needs_draft=True

SLACK_MESSAGE = {
    "source": "slack",
    "message_id": "slack_1747137600.000100",
    "thread_id": "1747137600.000100",
    "sender": "alice",
    "subject": "",
    "body": "hey pablo can you review my PR when you get a chance? it's blocking my deploy. link: github.com/company/repo/pull/142",
    "received_at": "2026-05-13T11:00:00Z",
}

# ── Raw Gmail webhook payload (before ingestion) ──────────────────────────────

RAW_GMAIL_EVENT = {
    "source": "gmail_work",
    "message_id": "msg-recruiter-001",
    "thread_id": "thread-recruiter-001",
    "sender": "sarah.johnson@meta.com",
    "subject": "Senior ML Engineer opportunity at Meta — Ranking team",
    "body": RECRUITER_EMAIL["body"],
    "received_at": "2026-05-13T09:15:00Z",
}

# ── Raw Slack Events API payload (before ingestion) ───────────────────────────

RAW_SLACK_EVENT = {
    "source": "slack",
    "type": "event_callback",
    "event": {
        "type": "message",
        "user": "alice",
        "text": "hey pablo can you review my PR when you get a chance? it's blocking my deploy. link: github.com/company/repo/pull/142",
        "ts": "1747137600.000100",
        "channel": "C123456",
    },
}

# ── Email with email signature to be stripped ────────────────────────────────

EMAIL_WITH_SIGNATURE = {
    "source": "gmail_work",
    "message_id": "msg-sig-001",
    "thread_id": "thread-sig-001",
    "sender": "partner@vendor.com",
    "subject": "Partnership proposal",
    "body": (
        "Hi Pablo,\n\n"
        "We'd love to explore a partnership with your team.\n\n"
        "--\n"
        "John Smith\n"
        "VP Sales, Vendor Corp\n"
        "john@vendor.com | +1 555 000 0000\n"
    ),
    "received_at": "2026-05-13T13:00:00Z",
}
