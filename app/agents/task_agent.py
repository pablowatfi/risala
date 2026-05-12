"""
Extracts action items from the message and persists them to the DB.
Runs for every message; returns an empty list if no tasks found.
"""
import json
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.graph.state import MessageState
from app.llm import get_llm
from app.db.session import AsyncSessionLocal
from app.db.models import Task


class ExtractedTask(BaseModel):
    task: str = Field(description="The action item, as a short imperative sentence")
    due_date: str | None = Field(default=None, description="ISO date string if a deadline is mentioned, else null")
    owner: str | None = Field(default=None, description="Person responsible if mentioned, else null")


class TaskList(BaseModel):
    tasks: list[ExtractedTask] = Field(description="All action items found. Empty list if none.")


_PROMPT = """You are an assistant that extracts action items from messages.

From: {sender}
Subject: {subject}
Body:
{body}

Extract every explicit action item. Include deadlines and owners when clearly stated.
Return an empty list if there are no action items."""


async def task_node(state: MessageState) -> dict:
    msg = state["normalized_message"]
    llm = get_llm("fast").with_structured_output(TaskList)

    result: TaskList = await llm.ainvoke(
        _PROMPT.format(
            sender=msg.get("sender", ""),
            subject=msg.get("subject", "") or "(no subject)",
            body=(msg.get("body", "") or "")[:3000],
        )
    )

    tasks_data = [t.model_dump() for t in result.tasks]

    # Persist to DB if we have a message row already
    db_message_id = state.get("db_message_id")
    if db_message_id and tasks_data:
        async with AsyncSessionLocal() as session:
            for t in tasks_data:
                due = None
                if t.get("due_date"):
                    try:
                        due = datetime.fromisoformat(t["due_date"]).replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                session.add(Task(
                    message_id=db_message_id,
                    task=t["task"],
                    due_date=due,
                    owner=t.get("owner"),
                ))
            await session.commit()

    return {"tasks": tasks_data}
