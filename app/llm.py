from typing import Literal
from langchain_core.language_models import BaseChatModel
from app.config import settings

Tier = Literal["smart", "fast"]


def get_llm(tier: Tier = "fast") -> BaseChatModel:
    model = settings.LLM_SMART_MODEL if tier == "smart" else settings.LLM_FAST_MODEL
    provider = settings.LLM_PROVIDER

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, base_url=settings.OLLAMA_BASE_URL)

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=settings.GROQ_API_KEY)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Choose ollama | groq | openai")
