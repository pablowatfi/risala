"""
Runs Tavily web search and summarises the results.
Only executes when classification.needs_research is True.

Query generation: a fast LLM call converts the email content into a focused search
query before hitting Tavily. This means for a recruiter email mentioning a technical
interview, the query becomes something like "Meta ML engineer interview experience
Glassdoor leetcode" rather than just the sender address and subject line.
"""
from app.graph.state import MessageState
from app.integrations.websearch import web_search
from app.llm import get_llm

_QUERY_PROMPT = """You are helping an inbox assistant research context for a message the user received.

From: {sender}
Subject: {subject}
Body:
{body}

Generate ONE focused web search query that would surface the most useful background
information to help the user respond to this message.

Think about what the user would actually want to know:
- Recruiter email for an ML role at Meta → "Meta ML engineer interview experience Glassdoor leetcode"
- Email about a technical interview including live coding → "{{company}} {{role}} technical interview experience leetcode"
- Email from an unfamiliar company proposing a partnership → "{{company}} reviews reputation funding"
- Email from a VC firm → "{{vc_firm}} portfolio investment thesis"

Return ONLY the search query string, nothing else."""

_SUMMARY_PROMPT = """You are a research assistant preparing a briefing for an inbox assistant.

The user received this message:
From: {sender}
Subject: {subject}
Body:
{body}

Web search results:
{results}

Write a 3-5 sentence briefing that gives the user useful context before they respond.
Ground the briefing in the specific details of the email above — for example, if it mentions
an interview, summarise what those interviews are typically like; if it mentions a company,
explain what they do and any relevant recent news.
Be factual and concise."""


async def research_node(state: MessageState) -> dict:
    if not state["classification"].get("needs_research"):
        return {}

    msg = state["normalized_message"]
    sender = msg.get("sender", "")
    subject = msg.get("subject", "") or ""
    body = (msg.get("body", "") or "")[:1000]

    # Use a fast LLM call to generate a context-aware search query from the email content
    query_llm = get_llm("fast")
    query_response = await query_llm.ainvoke(
        _QUERY_PROMPT.format(sender=sender, subject=subject, body=body)
    )
    query = query_response.content.strip().strip('"')

    results = await web_search(query)
    if not results:
        return {"research": {"summary": "No relevant research found.", "sources": []}}

    formatted = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['url']}\n{r['content']}"
        for i, r in enumerate(results[:5])
    )

    summary_llm = get_llm("smart")
    response = await summary_llm.ainvoke(
        _SUMMARY_PROMPT.format(
            sender=sender,
            subject=subject,
            body=body,
            results=formatted,
        )
    )

    return {
        "research": {
            "summary": response.content,
            "sources": [{"title": r["title"], "url": r["url"]} for r in results[:5]],
        }
    }
