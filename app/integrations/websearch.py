"""
Thin wrapper around Tavily for web search.
Falls back gracefully if TAVILY_API_KEY is not set.
"""
from app.config import settings


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Returns a list of {title, url, content} dicts."""
    if not settings.TAVILY_API_KEY:
        return []

    from tavily import AsyncTavilyClient
    client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)

    response = await client.search(
        query=query,
        search_depth="basic",
        max_results=max_results,
        include_answer=False,
    )

    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in response.get("results", [])
    ]
