# MessageOS (Local Agentic Inbox Assistant) --- Product & Engineering Spec

## 1. Goal

Build a **local-first AI assistant** that monitors:

-   2 Gmail accounts

and performs:

1.  email ingestion and classification
2.  job posting detection and research (LinkedIn & Wellfound digest emails)
3.  CV-based match scoring and application priority tagging
4.  company research (Glassdoor, Reddit, salary data)
5.  Telegram-based user interaction (alerts, links, follow-up actions)

The system must use **LangGraph** for orchestration.

User interaction is handled exclusively via **Telegram**.

------------------------------------------------------------------------

## 2. Non-negotiable rules

### Rule 1 --- NEVER SEND EMAIL

System may NOT send, reply to, or draft emails under any circumstances.
Email is **ingestion-only**.

### Rule 2 --- HUMAN IN LOOP

Any external action requires Telegram approval (inline button tap).
The system surfaces information and waits; it never acts autonomously.

------------------------------------------------------------------------

## 3. High-level architecture

``` text
Gmail (2) ---------> ingestion -> LangGraph -> action router -> Telegram (alerts + buttons)

                          ↓
                       PostgreSQL
                       Redis
```

Local deployment only.

------------------------------------------------------------------------

## 4. Tech stack

Backend: - Python 3.12 - FastAPI

Agents: - LangGraph - LangChain

Notifications / UX: - Telegram Bot API (`python-telegram-bot`)

LLM:

Provider is selected via `LLM_PROVIDER` in `.env`. Two model tiers are
used per-agent (`LLM_SMART_MODEL`, `LLM_FAST_MODEL`):

| `LLM_PROVIDER` | Smart model (complex tasks) | Fast model (classification) | Cost |
|---|---|---|---|
| `ollama` *(default for dev)* | `llama3.3` | `llama3.2` | Free (local) |
| `groq` *(free cloud)* | `llama-3.3-70b-versatile` | `llama-3.1-8b-instant` | Free tier |
| `openai` *(production)* | `gpt-4o` | `gpt-4o-mini` | Paid |

Smart model used for: job match scoring, company research summarization, cover letter generation.
Fast model used for: classification, deduplication checks, lightweight extraction.

All providers are supported by LangChain — swapping requires only the `.env` change; no code changes needed.

Search: - Tavily API (web search for Research Agent)

Database: - PostgreSQL (Docker) - Redis (state/cache)

Optional: - pgvector

Containerization: - Docker Compose

------------------------------------------------------------------------

## 5. Local deployment requirements

The Telegram webhook requires a publicly accessible URL.
Use **ngrok** (or localtunnel) to expose localhost during development.

``` bash
ngrok http 8000   # exposes FastAPI; copy the forwarding URL into .env
```

Gmail uses **scheduled polling** (no public URL needed for email).

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

Use: - Scheduled polling 3× daily (`POLL_TIMES` in `.env`) - OAuth

Scopes: - gmail.readonly - gmail.modify (optional labeling only)

Supported accounts: - work - personal

Deduplication: Gmail's history API is used. The app stores the last `historyId`
per account in `GMAIL_POLL_STATE_FILE`. On each poll only messages added since
the previous run are fetched. On first startup the current position is bookmarked
without processing any existing inbox emails.

**Not supported:** Slack, Google Calendar.

------------------------------------------------------------------------

## 7. Core agents (LangGraph)

### A. Ingestion Agent

Input: gmail event

Tasks: - normalize - clean signatures - deduplicate - detect source type (job digest vs regular email)

Output:

``` json
{
  "message_id": "...",
  "source": "gmail_work",
  "sender": "...",
  "subject": "...",
  "body": "...",
  "thread_id": "...",
  "received_at": "2024-01-01T09:00:00Z",
  "type": "job_digest" | "email"
}
```

------------------------------------------------------------------------

### B. Triage Agent

Determine: - urgency - category - confidence

Categories: - job_digest - informational

For `job_digest` emails the flow is handed off to the Job Pipeline Agent.
All other emails are classified as `informational` and discarded; no further action.

Output:

``` json
{
  "priority": "high",
  "category": "job_digest"
}
```

------------------------------------------------------------------------

### C. Job Pipeline Agent

Triggered when `category == "job_digest"` (emails from LinkedIn or Wellfound).

#### C1. Job Extraction

Parse the digest email body and extract each individual job offer:
- Job title
- Company name
- Location / remote status
- Application URL

#### C2. Deduplication

Cross-reference extracted jobs against the `job_postings` table.
Discard any job whose `external_id` (derived from URL or company+title hash) already exists.

#### C3. Location / Remote Filter

Apply source-specific rules before any further processing:

| Source | Rule |
|---|---|
| LinkedIn | Accept if location mentions Argentina or is labeled "remote from Argentina" |
| Wellfound | Accept only if description contains "full remote", "fully remote", or equivalent |

Discard jobs that do not pass their source filter.

#### C4. CV Match Scoring

For each passing job:

- Load CV documents from `CV_PDF_DIR` (PDF files) and `CV_JOBS_DIR` (Word `.docx` detailed job descriptions) — both configured in `.env`
- Compare job description against CV content using the smart LLM
- Output a match tag: `low` | `medium` | `high`

#### C5. Company Research (medium + high only)

For jobs tagged `medium` or `high`, run web research via Tavily:

- Glassdoor rating and recent reviews summary
- Reddit threads mentioning the company (culture, layoffs, interviews)
- Typical salary range for the role
- Recent company news

Output a structured `research_summary` stored in the `job_research` table.

------------------------------------------------------------------------

### D. Telegram Notification Agent

Posts to: personal Telegram chat with the user (`TELEGRAM_CHAT_ID`)

#### Job digest alert

Sends one consolidated message per processed digest containing all `medium` and `high` jobs:

```
💼 New Job Matches — LinkedIn / Wellfound

🟢 HIGH MATCH
• Senior Backend Engineer @ Stripe (Remote)
  Research: 4.1★ Glassdoor · "good WLB" on Reddit · ~$180k
  [Apply] [Research Company] [Cover Letter]

🟡 MEDIUM MATCH
• Staff Engineer @ Vercel (Remote)
  Research: 4.3★ Glassdoor · Competitive salaries reported
  [Apply] [Research Company] [Cover Letter]

(3 low-match jobs discarded)
```

Button callbacks:

| Button | Action |
|---|---|
| `[Apply]` | Posts the direct application URL |
| `[Research Company]` | Posts full company research summary |
| `[Cover Letter]` | Generates a tailored cover letter draft (never sends) |

------------------------------------------------------------------------

## 8. LangGraph state

``` python
class MessageState(TypedDict):
    raw_event: dict
    normalized_message: dict
    classification: dict
    # job pipeline fields (populated only for job_digest type)
    extracted_jobs: list
    filtered_jobs: list
    scored_jobs: list          # each entry includes match_tag
    job_research: dict | None  # keyed by job id
    user_decision: str | None
```

------------------------------------------------------------------------

## 9. LangGraph flow

``` text
START
  ↓
ingestion
  ↓
triage
  ↓
[if job_digest]
  ↓
  job_extraction
  ↓
  deduplication
  ↓
  location_filter
  ↓
  cv_match_scoring
  ↓
  company_research  (medium + high only, runs in parallel per job)
  ↓
  telegram_notification
  ↓
  WAIT
  ↓
  human taps Telegram button
  ↓
  execute approved action  (post link / research / cover letter draft)

[if informational]
  ↓
  do nothing
```

Must support pause/resume using LangGraph checkpoints.

------------------------------------------------------------------------

## 10. Database schema

Only job-related data is persisted. Non-job-digest emails are discarded without storage.

### job_postings

``` sql
id
source           -- 'linkedin' | 'wellfound'
external_id      -- hash of URL or company+title, used for deduplication
title
company
location
apply_url
description      -- job description snippet extracted from digest
match_tag        -- 'low' | 'medium' | 'high'
cover_letter     -- generated draft text (nullable, populated on demand)
status           -- 'new' | 'notified' | 'applied' | 'dismissed'
created_at
```

### job_research

``` sql
id
job_posting_id   -- FK to job_postings
glassdoor_summary
reddit_summary
salary_range
news_summary
sources_json
created_at
```

### actions

``` sql
id
job_posting_id
action_type      -- 'apply_link' | 'research_company' | 'cover_letter' | 'dismiss'
status           -- 'pending' | 'approved' | 'rejected'
created_at
```

------------------------------------------------------------------------

## 11. Telegram UX

All alerts go to the user's personal Telegram chat with the bot.

Example job digest alert:

```
💼 New Job Matches — 3 found (LinkedIn + Wellfound)

🟢 HIGH — Senior Backend Engineer @ Stripe
   Remote · Wellfound
   ⭐ 4.1 Glassdoor · Competitive pay · "Great eng culture" (Reddit)
   💰 ~$170k–$190k

   [Apply ↗]  [Research Company]  [Cover Letter]

─────────────────────────────
🟡 MEDIUM — Staff Engineer @ Vercel
   Remote · LinkedIn (Argentina)
   ⭐ 4.3 Glassdoor · Fast-growing · No recent layoffs
   💰 ~$150k–$180k

   [Apply ↗]  [Research Company]  [Cover Letter]

─────────────────────────────
(4 low-match positions discarded)
```

Button callbacks hit `POST /telegram/webhook`.

**After a button is tapped**, the bot posts a new message:

| Button | New message contains |
|---|---|
| `[Apply ↗]` | Direct application URL |
| `[Research Company]` | Full Glassdoor / Reddit / salary / news summary |
| `[Cover Letter]` | Tailored cover letter draft in a code block (never sent) |

------------------------------------------------------------------------

## 12. CV document configuration

``` env
CV_PDF_DIR=./cv_docs/pdf        # one or more PDF CV files
CV_JOBS_DIR=./cv_docs/jobs      # Word .docx files with detailed past job descriptions
```

These files are loaded at startup and cached. The smart LLM uses their
content to score CV–job fit and generate cover letters.

------------------------------------------------------------------------

## 13. Security

Secrets in: `.env`

Never log: - email bodies raw - tokens

Use: - encrypted tokens - local only

------------------------------------------------------------------------

## 14. Folder structure

``` text
message_os/
 ├── app/
 │   ├── agents/
 │   │    ├── ingestion.py
 │   │    ├── triage.py
 │   │    ├── job_pipeline.py
 │   │    ├── research.py
 │   │    └── telegram_notify.py
 │   ├── graph/
 │   ├── integrations/
 │   │    ├── gmail.py
 │   │    ├── telegram.py
 │   │    └── websearch.py
 │   ├── db/
 │   ├── api/
 │   └── main.py
 ├── cv_docs/
 │   ├── pdf/
 │   └── jobs/
 ├── tests/
 ├── docker-compose.yml
 ├── .env.example
 └── README.md
```

------------------------------------------------------------------------

## 15. MVP definition

Done when:

-   receives Gmail from both accounts
-   detects LinkedIn and Wellfound job digest emails
-   extracts individual job offers from digest emails
-   deduplicates against previously seen jobs
-   applies source-specific location/remote filters
-   scores each job against CV PDFs and past job descriptions
-   tags jobs as low / medium / high match
-   runs company research (Glassdoor, Reddit, salary) for medium and high matches
-   sends Telegram alert with job links, match tags, and research summary
-   responds to Telegram buttons: apply link, full research, cover letter draft
-   stores job postings and research in Postgres (non-job emails are discarded)
-   runs locally via Docker (+ ngrok for webhooks)

------------------------------------------------------------------------

## Explicitly out of scope

-   Slack ingestion (removed)
-   Google Calendar read or write (removed)
-   Email drafting or reply suggestions (removed)
-   Any automatic external action without explicit Telegram approval

------------------------------------------------------------------------

## Suggested future enhancements

-   semantic memory via pgvector for longer-term job preference learning
-   follow-up reminders for applied positions
-   daily job digest summary on demand via `/digest` Telegram command
-   application tracking (status updates per company)
