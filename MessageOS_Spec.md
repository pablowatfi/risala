# MessageOS (Local Agentic Inbox Assistant) --- Product & Engineering Spec

## 1. Goal

Build a **local-first AI assistant** that monitors:

-   2 Gmail accounts
-   Slack workspace(s)

and performs:

1.  message ingestion
2.  classification / prioritization
3.  task extraction
4.  research augmentation (web search before user reads)
5.  meeting recommendation (never auto-book)
6.  draft email/message suggestion (never auto-send)
7.  Slack-based user interaction

The system must use **LangGraph** for orchestration.

------------------------------------------------------------------------

## 2. Non-negotiable rules

### Rule 1 --- NEVER SEND EMAIL

System may: - draft emails

System may NOT: - send emails - reply automatically

### Rule 2 --- NEVER CONFIRM MEETINGS

System may: - inspect calendar - suggest slots - draft responses

System may NOT: - accept meetings - book meetings - decline meetings

without explicit human approval.

### Rule 3 --- HUMAN IN LOOP

Any external action requires Slack approval: - create calendar event -
send draft to clipboard - mark done

------------------------------------------------------------------------

## 3. High-level architecture

``` text
Gmail (2) ----\
               \
                -> ingestion -> LangGraph -> action router -> Slack
               /
Slack --------/

                    ↓
                 PostgreSQL
                    ↓
                  Redis
```

Local deployment only.

------------------------------------------------------------------------

## 4. Tech stack

Backend: - Python 3.12 - FastAPI

Agents: - LangGraph - LangChain

LLM:

Provider is selected via `LLM_PROVIDER` in `.env`. Two model tiers are
used per-agent (`LLM_SMART_MODEL`, `LLM_FAST_MODEL`):

| `LLM_PROVIDER` | Smart model (complex tasks) | Fast model (classification) | Cost |
|---|---|---|---|
| `ollama` *(default for dev)* | `llama3.3` | `llama3.2` | Free (local) |
| `groq` *(free cloud)* | `llama-3.3-70b-versatile` | `llama-3.1-8b-instant` | Free tier |
| `openai` *(production)* | `gpt-4o` | `gpt-4o-mini` | Paid |

Smart model used for: research summarization, draft generation, complex triage.  
Fast model used for: classification, urgency scoring, lightweight extraction.

All providers are supported by LangChain — swapping requires only the `.env` change; no code changes needed.

Search: - Tavily API (web search for Research Agent)

Database: - PostgreSQL (Docker) - Redis (state/cache)

Optional: - pgvector

Containerization: - Docker Compose

------------------------------------------------------------------------

## 5. Local deployment requirements

Gmail push notifications and Slack Events API both require a publicly
accessible URL. Use **ngrok** (or localtunnel) to expose localhost during
development.

``` bash
ngrok http 8000   # exposes FastAPI; copy the forwarding URL into .env
```

docker-compose:

``` yaml
services:
  postgres:
  redis:
  app:
```

Run:

``` bash
docker compose up
```

> Note: ngrok must be running before starting the app. The public URL
> must be set as `WEBHOOK_BASE_URL` in `.env`.

------------------------------------------------------------------------

## 6. Inputs

### Gmail

Use: - Gmail push notifications (requires `WEBHOOK_BASE_URL` via ngrok) - OAuth

Scopes: - gmail.readonly - gmail.modify (optional labeling only)

Supported accounts: - work - personal

### Slack

Use: - Slack Events API (requires `WEBHOOK_BASE_URL` via ngrok)

Listen: - DMs - mentions - app actions

### Calendar

Google Calendar readonly + freebusy.

May read: - free slots

May NOT create events automatically.

------------------------------------------------------------------------

## 7. Core agents (LangGraph)

### A. Ingestion Agent

Input: gmail/slack event

Tasks: - normalize - clean signatures - deduplicate

Output:

``` json
{
  "message_id": "...",
  "source": "gmail_work",
  "sender": "...",
  "subject": "...",
  "body": "...",
  "thread_id": "...",
  "received_at": "2024-01-01T09:00:00Z"
}
```

------------------------------------------------------------------------

### B. Triage Agent

Determine: - urgency - category - confidence

Categories: - urgent - task - meeting - research_needed - informational

Output:

``` json
{
  "priority":"high",
  "category":"meeting"
}
```

------------------------------------------------------------------------

### C. Research Agent

Trigger: if message requires external knowledge.

Examples: - company interview - product mentioned - news topic -
technology mentioned

Tool: **Tavily API** (`tavily-python` SDK, `TAVILY_API_KEY` in `.env`)

Actions: use web search: - company info - latest news - salary info -
interview prep info - docs/manuals - videos

Output:

``` json
{
  "summary":"Meta recruiter email. Company recently announced...",
  "sources":[]
}
```

This appears in Slack alert.

------------------------------------------------------------------------

### D. Task Agent

Extract: - tasks - deadlines - owner

Store in DB.

------------------------------------------------------------------------

### E. Meeting Agent

If meeting request:

Check: - calendar free slots

Generate options: - Tue 3pm - Wed 10am - Thu 4pm

Then ask on Slack:

Example: "Recruiter requests technical interview.

Available slots: 1. Tue 3pm 2. Wed 10am 3. Thu 4pm

Options: \[Suggest Slot\] \[Draft Email Asking Details\] \[Ignore\]"

Wait for user action.

------------------------------------------------------------------------

### F. Draft Agent

Creates: - suggested reply only

Never sends.

Store draft.

------------------------------------------------------------------------

### G. Slack Notification Agent

Posts to: `#message-os-alerts`

Only: - urgent - actionable

Digest: `#message-os-digest` — fires **3× daily** at times set via `.env`:

```
DIGEST_TIMES=08:00,12:30,19:00   # system local timezone
```

Each digest covers new messages since the previous digest window.

------------------------------------------------------------------------

## 8. LangGraph state

``` python
class MessageState(TypedDict):
    raw_event: dict
    normalized_message: dict
    classification: dict
    research: dict | None
    tasks: list
    meeting_options: list
    draft: str | None
    user_decision: str | None
```

------------------------------------------------------------------------

## 9. LangGraph flow

When multiple conditions are true for a single message, agents run in
**sequential priority order** before the Slack notification is sent:

``` text
START
  ↓
ingestion
  ↓
triage
  ↓
[1] if research_needed  -> research_agent
  ↓
[2] if meeting          -> meeting_agent
  ↓
[3] if task             -> task_agent
  ↓
[4] if reply_needed     -> draft_agent
  ↓
slack_notification  (always runs if urgency >= medium)
  ↓
WAIT
  ↓
human action via Slack
  ↓
execute approved action
```

All intermediate results are merged into `MessageState` before
`slack_notification` runs, so the Slack alert can include research
context, available slots, extracted tasks, and a draft reply in one
message.

Must support pause/resume using LangGraph checkpoints.

------------------------------------------------------------------------

## 10. Database schema

### messages

``` sql
id
source           -- 'gmail_work' | 'gmail_personal' | 'slack'
sender
subject
body
thread_id        -- Gmail thread or Slack thread_ts
received_at
priority         -- 'high' | 'medium' | 'low'
category         -- 'urgent' | 'task' | 'meeting' | 'research_needed' | 'informational'
status           -- 'new' | 'reviewed' | 'actioned' | 'dismissed'
created_at
```

### tasks

``` sql
id
message_id
task
due_date
owner            -- extracted from message body (nullable)
status           -- 'open' | 'done'
created_at
```

### research

``` sql
id
message_id
summary
sources_json
```

### drafts

``` sql
id
message_id
draft_text
approved         -- boolean, default false
created_at
```

### actions

``` sql
id
message_id
action_type      -- 'suggest_slots' | 'show_draft' | 'ask_more_info' | 'dismiss'
status           -- 'pending' | 'approved' | 'rejected'
created_at
```

------------------------------------------------------------------------

## 11. Slack UX

Channel: `#message-os-alerts`

Example: "🚨 Meta recruiter email

Detected: - category: meeting - urgency: high

Research: - likely recruiter outreach - typical loop: coding + ML system
design

Actions: \[Show Draft\] \[Suggest Slots\] \[Ask for More Info\]
\[Dismiss\]"

Buttons call the FastAPI backend webhook (`/slack/actions`).

**After a button is pressed**, the bot posts a **new message** in
`#message-os-alerts` with the result:

| Button | New message contains |
|---|---|
| `[Show Draft]` | Full draft text + `[Copy to Clipboard]` |
| `[Suggest Slots]` | Available slots + `[Confirm Slot X]` buttons |
| `[Ask for More Info]` | Draft clarification email + `[Copy to Clipboard]` |
| `[Dismiss]` | Confirmation that the alert was dismissed |

Meeting slots use the **system local timezone**. Number of slots
suggested: 3 (configurable via `MEETING_SLOT_COUNT` in `.env`).

Digest channel: `#message-os-digest`, fires at 8:00 / 12:30 / 19:00
(local time). Each digest summarises messages received since the previous
digest window.

------------------------------------------------------------------------

## 12. Security

Secrets in: `.env`

Never log: - email bodies raw - tokens

Use: - encrypted tokens - local only

------------------------------------------------------------------------

## 13. Folder structure

``` text
message_os/
 ├── app/
 │   ├── agents/
 │   ├── graph/
 │   ├── integrations/
 │   │    ├── gmail.py
 │   │    ├── slack.py
 │   │    ├── calendar.py
 │   │    └── websearch.py
 │   ├── db/
 │   ├── api/
 │   └── main.py
 ├── tests/
 ├── docker-compose.yml
 ├── .env.example
 └── README.md
```

------------------------------------------------------------------------

## 14. MVP definition

Done when:

-   receives Gmail from both accounts
-   receives Slack messages
-   classifies urgency and category
-   extracts tasks and stores them in Postgres
-   runs research automatically when useful (via Tavily)
-   posts to Slack alerts with action buttons
-   suggests meeting slots but does not book
-   drafts replies but does not send
-   stores everything in Postgres
-   runs locally via Docker (+ ngrok for webhooks)

------------------------------------------------------------------------

## Suggested future enhancements

-   Google Calendar write access with explicit approval
-   semantic memory via pgvector
-   follow-up reminders
-   daily planning agent
