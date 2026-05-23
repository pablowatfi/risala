"""
Langfuse observability integration.
Returns a configured LangChain callback handler, or None if keys are not set.
Each pipeline invocation gets its own handler so each email is a separate trace.
"""
from app.config import settings


def get_langfuse_handler(trace_name: str = "job_pipeline"):
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    from langfuse.callback import CallbackHandler
    return CallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        trace_name=trace_name,
    )
