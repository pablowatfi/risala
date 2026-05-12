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
# Create and activate a local virtualenv (required on macOS with Homebrew Python)
python3 -m venv .venv
source .venv/bin/activate

# Install the Google dependencies
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Authorise work account
python3 -c "from app.integrations.gmail import run_oauth_flow; run_oauth_flow('gmail_work')"

# Authorise personal account
python3 -c "from app.integrations.gmail import run_oauth_flow; run_oauth_flow('gmail_personal')"
```

> The `.venv` is only needed for the OAuth step. The app itself runs inside Docker and does not use it.

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

### 4. Telegram bot

#### 4a. Create the bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts (pick any name and username)
3. BotFather replies with a token like `123456789:ABCdef...` — copy it into `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   ```

#### 4b. Get your chat ID

1. Search for your new bot in Telegram and send it `/start`
2. Open this URL in your browser (replace with your token):
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
3. Find `"chat": {"id": 123456789}` in the response — that number is your chat ID
4. Add it to `.env`:
   ```env
   TELEGRAM_CHAT_ID=123456789
   ```

#### 4c. Register the webhook

The app registers the webhook automatically on startup — no manual steps needed.  
It calls `setWebhook` pointing to `WEBHOOK_BASE_URL/telegram/webhook`.

> Make sure ngrok is running and `WEBHOOK_BASE_URL` is set before starting the app.

#### 4d. Available bot commands

Once running, you can message the bot directly:

| Command | Effect |
|---|---|
| `/start` | Shows a welcome message and command list |
| `/status` | Shows current LLM provider and system status |
| `/digest` | Triggers an on-demand digest right now |

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
| `TELEGRAM_BOT_TOKEN` | — | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | — | Your personal chat ID with the bot |
| `DIGEST_TIMES` | `08:00,12:30,19:00` | Comma-separated HH:MM digest schedule |
| `MEETING_SLOT_COUNT` | `3` | Number of calendar slots to suggest |
| `MEETING_LOOKAHEAD_DAYS` | `7` | How many days ahead to look for slots |
| `WEBHOOK_BASE_URL` | — | Your ngrok public URL |
| `TAVILY_API_KEY` | — | Optional; disables research if absent |

---

## How alerts look

Alerts arrive as Telegram messages with inline keyboard buttons:

```
🚨 Meeting Request: Technical Interview

From: recruiter@meta.com
Source: gmail_work
Priority: High

Research:
Meta recently announced Q3 earnings beat expectations. The team is
hiring ML engineers for the Ranking team. Typical loop: coding screen
+ ML system design + behavioural.

Available slots:
1. Tue Jan 14, 3:00 PM
2. Wed Jan 15, 10:00 AM
3. Thu Jan 16, 4:00 PM

┌─────────────┬───────────────┐
│  Show Draft │ Suggest Slots │
├─────────────┴───────────────┤
│  Ask for More Info          │
├─────────────────────────────┤
│  ❌ Dismiss                 │
└─────────────────────────────┘
```

Tapping a button sends a new message in your chat with the result (draft text, slot confirmation, etc.).

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
