from typing import TypedDict, Optional


class MessageState(TypedDict):
    # Raw payload received from Gmail or Slack webhook
    raw_event: dict

    # Normalised fields after ingestion agent
    normalized_message: dict  # {message_id, source, sender, subject, body, thread_id, received_at}

    # Triage output
    classification: dict      # {priority, category, needs_research, needs_draft, reasoning}

    # Research agent output (None if not triggered)
    research: Optional[dict]  # {summary, sources}

    # Task agent output
    tasks: list               # [{task, due_date, owner}]

    # Meeting agent output
    meeting_options: list     # [{start, end, label}]

    # Draft agent output
    draft: Optional[str]

    # Set after human clicks a Slack action button
    user_decision: Optional[str]

    # DB primary key of the saved Message row
    db_message_id: Optional[int]

    # Propagated error message (non-fatal; pipeline continues)
    error: Optional[str]
