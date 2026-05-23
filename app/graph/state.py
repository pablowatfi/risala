from typing import TypedDict, Optional


class MessageState(TypedDict):
    # Raw payload received from Gmail webhook
    raw_event: dict

    # Normalised fields after ingestion agent
    # Includes job_source: "linkedin" | "wellfound" | None
    normalized_message: dict

    # Triage output: {category: "job_digest" | "informational"}
    classification: dict

    # Job pipeline fields (populated only for job_digest emails)
    extracted_jobs: list       # raw parsed jobs from digest body
    filtered_jobs: list        # after dedup + location/remote filter
    scored_jobs: list          # each entry includes match_tag: low|medium|high

    # Company research keyed by job external_id (medium + high only)
    job_research: Optional[dict]

    # Set after human taps a Telegram inline button
    user_decision: Optional[str]

    # Propagated error message (non-fatal; pipeline continues)
    error: Optional[str]
