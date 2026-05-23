"""
Job Pipeline Agent — runs for every job_digest email (LinkedIn / Wellfound).

Sub-steps:
  C1. Job Extraction   — parse digest body into individual job offers (LLM)
  C2. Deduplication    — discard jobs already in job_postings table
  C3. Location Filter  — LinkedIn: Argentina; Wellfound: full remote
  C4. CV Match Scoring — compare each job against user CV docs (smart LLM)
  C5. Company Research — Glassdoor/Reddit/salary for medium + high (Tavily)
"""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import JobPosting, JobResearch
from app.db.session import AsyncSessionLocal
from app.graph.state import MessageState
from app.integrations.websearch import web_search
from app.llm import get_llm
from app.agents.research import load_cv_text


# ── C1: Job Extraction ────────────────────────────────────────────────────────

class ExtractedJob(BaseModel):
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str = Field(default="", description="Location or remote status as shown in the email")
    apply_url: str = Field(default="", description="Direct URL to the job application page")
    description: str = Field(default="", description="Brief description or snippet if available")


class JobList(BaseModel):
    jobs: list[ExtractedJob] = Field(description="All individual job postings found in the email")


_EXTRACT_PROMPT = """You are parsing a job digest email from {source}.
Extract every individual job posting listed in the email body.

For each job extract:
- title: the job title
- company: the company name
- location: the location or remote status as written (e.g. "Remote", "Buenos Aires, Argentina", "Full Remote")
- apply_url: the direct link to apply or view the job (LinkedIn or Wellfound URL)
- description: any short description or skill tags listed (empty string if none)

Email body:
{body}

Return all jobs found. If none, return an empty list."""


async def _extract_jobs(body: str, source: str) -> list[dict]:
    llm = get_llm("smart").with_structured_output(JobList)
    result: JobList = await llm.ainvoke(
        _EXTRACT_PROMPT.format(source=source, body=body[:4000])
    )
    return [j.model_dump() for j in result.jobs]


# ── C2: Deduplication ─────────────────────────────────────────────────────────

def _make_external_id(apply_url: str, company: str, title: str) -> str:
    key = apply_url.strip() if apply_url.strip() else f"{company.lower()}|{title.lower()}"
    return hashlib.md5(key.encode()).hexdigest()


async def _known_external_ids() -> set[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(JobPosting.external_id))
        return set(result.scalars().all())


# ── C3: Location / Remote Filter ──────────────────────────────────────────────

_REMOTE_KEYWORDS = {"full remote", "fully remote", "fully-remote", "100% remote", "remote"}


def _passes_filter(job: dict, source: str) -> bool:
    loc = (job.get("location") or "").lower()
    desc = (job.get("description") or "").lower()
    combined = loc + " " + desc

    if source == "linkedin":
        return "argentina" in combined

    if source == "wellfound":
        return any(kw in combined for kw in _REMOTE_KEYWORDS)

    return False



# ── C4: CV Match Scoring ──────────────────────────────────────────────────────

class MatchResult(BaseModel):
    match_tag: Literal["low", "medium", "high"] = Field(
        description="low=poor fit, medium=partial fit, high=strong fit"
    )
    reasoning: str = Field(description="One sentence explaining the match rating")


_SCORE_PROMPT = """Rate how well this job matches the candidate's profile.

=== Candidate CV and Experience ===
{cv_text}

=== Job ===
Title: {title}
Company: {company}
Location: {location}
Description: {description}

Rating guide:
- high: strong skills/experience alignment, very relevant role
- medium: partial alignment, some relevant experience
- low: poor match, missing most key requirements

Return match_tag and a one-sentence reasoning."""


async def _score_job(job: dict, cv_text: str) -> dict:
    llm = get_llm("smart").with_structured_output(MatchResult)
    result: MatchResult = await llm.ainvoke(
        _SCORE_PROMPT.format(
            cv_text=cv_text[:3000],
            title=job["title"],
            company=job["company"],
            location=job.get("location", ""),
            description=(job.get("description") or "")[:500],
        )
    )
    return {**job, "match_tag": result.match_tag, "match_reasoning": result.reasoning}


# ── C5: Company Research ──────────────────────────────────────────────────────

_RESEARCH_SUMMARY_PROMPT = """Summarise company research for a job candidate.

Company: {company}
Role: {title}

Search results:
{results}

Extract and return a JSON object with these fields:
- glassdoor_summary: rating and key review themes (1-2 sentences, or null)
- reddit_summary: culture/WLB/interview themes from Reddit (1-2 sentences, or null)
- salary_range: typical salary range for this role (e.g. "$120k-$160k", or null)
- news_summary: recent notable company news (1 sentence, or null)

Return only valid JSON."""


async def _research_company(job: dict) -> dict:
    company = job["company"]
    title = job["title"]

    queries = [
        f"{company} Glassdoor reviews rating",
        f"{company} {title} salary",
        f"{company} reddit employees culture work life balance",
    ]

    all_results: list[dict] = []
    for query in queries:
        results = await web_search(query, max_results=3)
        all_results.extend(results)

    if not all_results:
        return {"glassdoor_summary": None, "reddit_summary": None,
                "salary_range": None, "news_summary": None, "sources": []}

    formatted = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['url']}\n{r['content']}"
        for i, r in enumerate(all_results[:9])
    )

    llm = get_llm("smart")
    response = await llm.ainvoke(
        _RESEARCH_SUMMARY_PROMPT.format(company=company, title=title, results=formatted)
    )

    try:
        text = response.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        summary = json.loads(text)
    except Exception:
        summary = {"glassdoor_summary": None, "reddit_summary": None,
                   "salary_range": None, "news_summary": None}

    summary["sources"] = [{"title": r["title"], "url": r["url"]} for r in all_results[:9]]
    return summary


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist(scored_jobs: list[dict], research: dict) -> dict:
    """Save new job postings and their research to DB. Returns mapping external_id → db_id."""
    id_map: dict[str, int] = {}
    async with AsyncSessionLocal() as session:
        for job in scored_jobs:
            ext_id = job["external_id"]
            posting = JobPosting(
                source=job["source"],
                external_id=ext_id,
                title=job["title"],
                company=job["company"],
                location=job.get("location"),
                apply_url=job.get("apply_url"),
                description=job.get("description"),
                match_tag=job.get("match_tag"),
                status="new",
            )
            session.add(posting)
            await session.flush()
            id_map[ext_id] = posting.id

            if ext_id in research:
                r = research[ext_id]
                session.add(JobResearch(
                    job_posting_id=posting.id,
                    glassdoor_summary=r.get("glassdoor_summary"),
                    reddit_summary=r.get("reddit_summary"),
                    salary_range=r.get("salary_range"),
                    news_summary=r.get("news_summary"),
                    sources_json=json.dumps(r.get("sources", [])),
                ))

        await session.commit()
    return id_map


# ── Node ──────────────────────────────────────────────────────────────────────

async def job_pipeline_node(state: MessageState) -> dict:
    msg = state["normalized_message"]
    source = msg.get("job_source", "")
    body = msg.get("body", "")

    # C1: Extract
    extracted_jobs = await _extract_jobs(body, source)
    if not extracted_jobs:
        return {"extracted_jobs": [], "filtered_jobs": [], "scored_jobs": [], "job_research": None}

    # C2: Deduplicate
    known = await _known_external_ids()
    new_jobs = []
    for job in extracted_jobs:
        ext_id = _make_external_id(job.get("apply_url", ""), job["company"], job["title"])
        if ext_id not in known:
            new_jobs.append({**job, "external_id": ext_id, "source": source})

    if not new_jobs:
        return {"extracted_jobs": extracted_jobs, "filtered_jobs": [], "scored_jobs": [], "job_research": None}

    # C3: Filter
    filtered_jobs = [j for j in new_jobs if _passes_filter(j, source)]
    if not filtered_jobs:
        return {"extracted_jobs": extracted_jobs, "filtered_jobs": [], "scored_jobs": [], "job_research": None}

    # C4: CV Match Scoring
    cv_text = load_cv_text()
    scored_jobs = []
    for job in filtered_jobs:
        scored = await _score_job(job, cv_text)
        scored_jobs.append(scored)

    # C5: Company Research (medium + high only)
    research: dict = {}
    for job in scored_jobs:
        if job.get("match_tag") in ("medium", "high"):
            research[job["external_id"]] = await _research_company(job)

    # Persist to DB
    id_map = await _persist(scored_jobs, research)

    # Annotate scored_jobs with db_id for Telegram buttons
    for job in scored_jobs:
        job["db_id"] = id_map.get(job["external_id"])

    return {
        "extracted_jobs": extracted_jobs,
        "filtered_jobs": filtered_jobs,
        "scored_jobs": scored_jobs,
        "job_research": research if research else None,
    }
