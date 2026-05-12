"""
Runs Tavily web search and summarises the results.
Only executes when classification.needs_research is True.
"""
from app.graph.state import MessageState
from app.integrations.websearch import web_search
from app.llm import get_llm

_SUMMARY_PROMPT = """You are a research assistant preparing a briefing for an inbox assistant.

The user received a message from: {sender}
Subject: {subject}

Web search results:
{results}

Write a 3-5 sentence briefing that gives the user useful context before they respond.
Focus on: who the sender is, what their company does, any relevant recent news, and anything
that would help the user craft a better reply. Be factual and concise."""


async def research_node(state: MessageState) -> dict:
    if not state["classification"].get("needs_research"):
        return {}

    msg = state["normalized_message"]
    sender = msg.get("sender", "")
    subject = msg.get("subject", "") or msg.get("body", "")[:100]

    # Build a focused search query
    query = f"{sender} {subject}".strip()

    results = await web_search(query)
    if not results:
        return {"research": {"summary": "No relevant research found.", "sources": []}}

    # Format results for the LLM
    formatted = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['url']}\n{r['content']}"
        for i, r in enumerate(results[:5])
    )

    llm = get_llm("smart")
    response = await llm.ainvoke(
        _SUMMARY_PROMPT.format(
            sender=sender,
            subject=subject,
            results=formatted,
        )
    )

    return {
        "research": {
            "summary": response.content,
            "sources": [{"title": r["title"], "url": r["url"]} for r in results[:5]],
        }
    }
