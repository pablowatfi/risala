"""
Shared fixtures, DB setup, and LLM-as-judge helper for all tests.
"""
import os
import pytest
import app.agents.job_pipeline as pipeline_module
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.models import Base


# ── In-memory SQLite DB (replaces Postgres for all tests) ────────────────────

@pytest.fixture(autouse=True)
async def test_db(monkeypatch):
    """Spin up a fresh in-memory SQLite DB for every test and patch all session factories."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(pipeline_module, "AsyncSessionLocal", TestSession)

    try:
        import app.api.telegram_webhook as wh_mod
        monkeypatch.setattr(wh_mod, "AsyncSessionLocal", TestSession)
    except ImportError:
        pass

    yield TestSession
    await engine.dispose()


# ── LLM-as-judge ─────────────────────────────────────────────────────────────

JUDGE_PASS_THRESHOLD = 7


class JudgeVerdict(BaseModel):
    score: int = Field(ge=0, le=10, description="Quality score 0-10")
    passed: bool = Field(description="True if score >= 7")
    reasoning: str = Field(description="Explanation of the score")
    issues: list[str] = Field(default_factory=list, description="Specific problems found")


async def llm_judge(output: str, criteria: str, context: str = "") -> JudgeVerdict:
    from app.llm import get_llm
    llm = get_llm("smart").with_structured_output(JudgeVerdict)

    prompt = f"""You are an expert evaluator for an AI job-matching assistant.
Your job is to assess whether an agent produced a correct and useful output.

Score 0-10 where:
  10 = perfect, exactly right
   7 = acceptable, minor issues only
   4 = partially correct but missing key things
   0 = completely wrong or harmful

Set passed=true if and only if score >= {JUDGE_PASS_THRESHOLD}.

{"=== Context ===\n" + context + "\n" if context else ""}
=== Agent Output ===
{output}

=== Evaluation Criteria ===
{criteria}

Be strict. A score of 7+ means you would trust this output to be shown to the user.
"""
    return await llm.ainvoke(prompt)


@pytest.fixture
def judge():
    return llm_judge


# ── Skip helpers ──────────────────────────────────────────────────────────────

def requires_llm():
    from app.config import settings
    if settings.LLM_PROVIDER == "ollama":
        import httpx
        try:
            r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3)
            if r.status_code != 200:
                return pytest.mark.skip(reason="Ollama not running")
        except Exception:
            return pytest.mark.skip(reason="Ollama not reachable")
    elif settings.LLM_PROVIDER == "groq" and not settings.GROQ_API_KEY:
        return pytest.mark.skip(reason="GROQ_API_KEY not set")
    elif settings.LLM_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
        return pytest.mark.skip(reason="OPENAI_API_KEY not set")
    return pytest.mark.skipif(False, reason="")


def requires_gmail(account: str = "gmail_work"):
    from app.config import settings
    token_file = (
        settings.GMAIL_WORK_TOKEN_FILE
        if account == "gmail_work"
        else settings.GMAIL_PERSONAL_TOKEN_FILE
    )
    return pytest.mark.skipif(
        not os.path.exists(token_file),
        reason=f"Gmail token not found: {token_file}",
    )
