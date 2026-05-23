from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))              # linkedin | wellfound
    external_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(500))
    apply_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    match_tag: Mapped[str | None] = mapped_column(String(10))    # low | medium | high
    cover_letter: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | notified | applied | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    research: Mapped[list["JobResearch"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    actions: Mapped[list["JobAction"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobResearch(Base):
    __tablename__ = "job_research"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"))
    glassdoor_summary: Mapped[str | None] = mapped_column(Text)
    reddit_summary: Mapped[str | None] = mapped_column(Text)
    salary_range: Mapped[str | None] = mapped_column(String(200))
    news_summary: Mapped[str | None] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["JobPosting"] = relationship(back_populates="research")


class JobAction(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"))
    action_type: Mapped[str] = mapped_column(String(50))   # apply_link | research_company | cover_letter | dismiss
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["JobPosting"] = relationship(back_populates="actions")
