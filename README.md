# MessageOS

A local-first AI assistant that monitors your Gmail inboxes and Slack workspace, classifies messages, extracts tasks, researches senders, suggests meeting slots, and drafts replies — all delivered to you via Slack with one-click action buttons.

**Nothing is ever sent or booked automatically.** Every external action requires your approval.

---

## What it does

When a new email or Slack message arrives, MessageOS runs it through a pipeline:

1. **Ingestion** — normalises the raw event, strips email signatures
2. **Triage** — classifies urgency (high / medium / low) and category (meeting, task, research, urgent, informational)
3. **Research** — if the sender or topic warrants it, searches the web via Tavily and prepares a briefing
4. **Meeting** — if it's a meeting request, checks your Google Calendar and finds free slots
5. **Task extraction** — pulls out action items and stores them in Postgres
6. **Draft** — generates a suggested reply
7. **Slack alert** — posts everything to `#message-os-alerts` with action buttons

Three times a day (8 am, 12:30 pm, 7 pm) a digest summary is posted to `#message-os-digest`.

---

## Architecture

```
Gmail (work + personal)  ──┐
                            ├──▶  FastAPI webhooks
Slack workspace            ──┘         │
                                       ▼
                               LangGraph pipeline
                          ┌────────────────────────┐
                          │  ingestion              │
                          │  triage (fast LLM)      │
                          │  research (Tavily)      │
                          │  meeting (Calendar API) │
                          │  task extraction        │
                          │  draft (smart LLM)      │
                          │  slack notification     │
                          └────────────────────────┘
                                       │
                             ┌─────────┴─────────┐
                          Postgres              Redis
                      (messages, tasks,     (LangGraph state)
                       drafts, actions)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Orchestration | LangGraph, LangChain |
| LLM | Ollama (default/free) · Groq (free cloud) · OpenAI (production) |
| Search | Tavily API |
| Database | PostgreSQL 16 |
| Cache / state | Redis 7 |
| Containerisation | Docker Compose |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [ngrok](https://ngrok.com/download) (free account) — exposes localhost to Gmail and Slack webhooks
- A Google Cloud project (for Gmail + Calendar)
- A Slack app (for sending alerts and receiving events)
- One of: Ollama running locally, a Groq API key, or an OpenAI API key

---

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/your-username/risala.git
cd risala
cp .env.example .env
```

Open `.env` and fill in the values as described in the sections below.

---

### 2. Choose your LLM provider

Edit `.env`:

```env
# Free local (requires Ollama running on your machine)
LLM_PROVIDER=ollama
LLM_SMART_MODEL=llama3.3
LLM_FAST_MODEL=llama3.2

# Free cloud (requires Groq API key)
LLM_PROVIDER=groq
LLM_SMART_MODEL=llama-3.3-70b-versatile
LLM_FAST_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_key_here

# Production (requires OpenAI API key)
LLM_PROVIDER=openai
LLM_SMART_MODEL=gpt-4o
LLM_FAST_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

**Ollama setup** (if using local models):
```bash
# Install Ollama: https://ollama.com
ollama pull llama3.3
ollama pull llama3.2
# Ollama must be running when you start the app
```

**Groq** — get a free API key at [console.groq.com](https://console.groq.com).

---

### 3. Gmail credentials

#### 3a. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. `messageos`)
3. Enable these APIs:
   - **Gmail API**
   - **Google Calendar API**
   - **Cloud Pub/Sub API** (for push notifications)

#### 3b. Create OAuth credentials

1. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Download the JSON file and save it as:
   ```
   credentials/gmail_credentials.json
   ```

#### 3c. Authorise both Gmail accounts

Run the OAuth flow once for each account. This opens a browser window and saves a token file.

```bash
# Install dependencies locally first (only needed for this step)
pip install google-auth-oauthlib google-api-python-client

# Authorise work account
python3 -c "from app.integrations.gmail import run_oauth_flow; run_oauth_flow('gmail_work')"

# Authorise personal account
python3 -c "from app.integrations.gmail import run_oauth_flow; run_oauth_flow('gmail_personal')"
```

Token files are saved to `credentials/gmail_work_token.json` and `credentials/gmail_personal_token.json`. These are refreshed automatically at runtime.

#### 3d. Set up Gmail push notifications (Pub/Sub)

Gmail delivers new-message events via Google Cloud Pub/Sub.

1. In Cloud Console → **Pub/Sub → Create topic**, name it `gmail-push`
2. Add the Gmail service account as a publisher:
   - Topic → **Permissions → Add principal**
   - Principal: `gmail-api-push@system.gserviceaccount.com`
   - Role: `Pub/Sub Publisher`
3. Create a **push subscription** pointing to your ngrok URL:
   - Subscription ID: `gmail-push-sub`
   - Delivery type: **Push**
   - Endpoint URL: `https://YOUR_NGROK_URL.ngrok-free.app/gmail/push`
4. Update `.env`:
   ```env
   GMAIL_PUBSUB_TOPIC=projects/YOUR_PROJECT_ID/topics/gmail-push
   GMAIL_WORK_ADDRESS=you@work.com
   GMAIL_PERSONAL_ADDRESS=you@personal.com
   ```

---

### 4. Slack app

#### 4a. Create the app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch**
2. Name it `MessageOS`, select your workspace

#### 4b. Configure Bot Token Scopes

Go to **OAuth & Permissions → Scopes → Bot Token Scopes** and add:

| Scope | Purpose |
|---|---|
| `chat:write` | Post messages and alerts |
| `channels:read` | Resolve channel names |
| `im:read` | Read DMs |
| `im:write` | Post in DMs |

Click **Install to Workspace** and copy the **Bot User OAuth Token** (`xoxb-...`) into `.env`:

```env
SLACK_BOT_TOKEN=xoxb-...
```

#### 4c. Enable Event Subscriptions

1. Go to **Event Subscriptions → Enable Events**
2. Request URL: `https://YOUR_NGROK_URL.ngrok-free.app/slack/events`
3. Slack will send a challenge — the app must be running to verify it (see step 6)
4. Subscribe to bot events:
   - `message.im` — direct messages
   - `app_mention` — @mentions

#### 4d. Enable Interactive Components

1. Go to **Interactivity & Shortcuts → Enable Interactivity**
2. Request URL: `https://YOUR_NGROK_URL.ngrok-free.app/slack/actions`

#### 4e. Copy the signing secret

**Basic Information → App Credentials → Signing Secret** → paste into `.env`:

```env
SLACK_SIGNING_SECRET=your_signing_secret
```

#### 4f. Create the alert channels

In Slack, create two channels and invite the MessageOS bot to each:

```
#message-os-alerts   — real-time alerts with action buttons
#message-os-digest   — 3× daily summary digest
```

Update `.env` if you use different channel names:

```env
SLACK_ALERTS_CHANNEL=#message-os-alerts
SLACK_DIGEST_CHANNEL=#message-os-digest
```

---

### 5. Tavily search (optional but recommended)

Research-augmented alerts require a Tavily API key. The free tier is sufficient for testing.

1. Sign up at [tavily.com](https://tavily.com)
2. Copy your API key into `.env`:
   ```env
   TAVILY_API_KEY=tvly-...
   ```

If `TAVILY_API_KEY` is empty, the research agent is silently skipped.

---

### 6. Start ngrok

ngrok exposes your local FastAPI server so Gmail and Slack can reach it.

```bash
ngrok http 8000
```

Copy the **Forwarding** URL (e.g. `https://abc123.ngrok-free.app`) into `.env`:

```env
WEBHOOK_BASE_URL=https://abc123.ngrok-free.app
```

> You need to update this URL every time ngrok restarts (unless you have a paid ngrok account with a fixed domain).
> After updating it, re-register the URL in both the Pub/Sub subscription and the Slack app settings.

---

### 7. Run

```bash
docker compose up
```

This starts:
- **postgres** — message storage (port 5432)
- **redis** — pipeline state cache (port 6379)
- **app** — FastAPI server (port 8000)

On first boot, the app creates all database tables automatically.

Check it's healthy:
```bash
curl http://localhost:8000/health
# {"status":"ok","llm_provider":"ollama"}
```

---

## Configuration reference

All settings live in `.env`. Key variables:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `groq` \| `openai` |
| `LLM_SMART_MODEL` | `llama3.3` | Model for drafts, research summaries |
| `LLM_FAST_MODEL` | `llama3.2` | Model for triage, task extraction |
| `DIGEST_TIMES` | `08:00,12:30,19:00` | Comma-separated HH:MM digest schedule |
| `MEETING_SLOT_COUNT` | `3` | Number of calendar slots to suggest |
| `MEETING_LOOKAHEAD_DAYS` | `7` | How many days ahead to look for slots |
| `WEBHOOK_BASE_URL` | — | Your ngrok public URL |
| `TAVILY_API_KEY` | — | Optional; disables research if absent |

---

## How alerts look

```
🚨  Meeting Request: Technical Interview — Meta Recruiter

From:       recruiter@meta.com        Source:  gmail_work
Priority:   High                      Category: Meeting Request

Research:
Meta recently announced Q3 earnings beat expectations. The team is
hiring ML engineers for the Ranking team. Typical loop: coding screen
+ ML system design + behavioural.

Available slots:
1. Tue Jan 14, 3:00 PM
2. Wed Jan 15, 10:00 AM
3. Thu Jan 16, 4:00 PM

[ Show Draft ]  [ Suggest Slots ]  [ Ask for More Info ]  [ Dismiss ]
```

Clicking a button posts a new message in `#message-os-alerts` with the result.

---

## Non-negotiable safety rules

These are hard-coded in the pipeline — no configuration can override them:

- **Emails are never sent.** Drafts are only stored in the database and shown on request.
- **Meetings are never booked.** The app is read-only on Google Calendar.
- **Every external action requires a button click.** The pipeline always pauses at the Slack notification and waits for human input.

---

## Project structure

```
risala/
 ├── app/
 │   ├── agents/          # 7 LangGraph pipeline nodes
 │   ├── api/             # FastAPI webhook routes
 │   ├── db/              # SQLAlchemy models and session
 │   ├── graph/           # LangGraph state and graph wiring
 │   ├── integrations/    # Gmail, Slack, Calendar, Tavily clients
 │   ├── config.py        # Typed settings from .env
 │   ├── llm.py           # LLM provider factory
 │   └── main.py          # App entry point, scheduler, lifespan
 ├── credentials/         # OAuth token files (git-ignored)
 ├── tests/
 ├── docker-compose.yml
 ├── Dockerfile
 ├── requirements.txt
 └── .env.example
```
