"""SQLAlchemy 2.0 declarative models for pelis-feed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "Movie", "FeedHealth"]


class Base(DeclarativeBase):
    """Base class for all pelis-feed ORM models."""

    pass


class Movie(Base):
    """A movie entry parsed from the RSS feed."""

    __tablename__ = "movies"
    __table_args__ = (
        Index("ix_movies_title_year", "title", "year"),
        Index("ix_movies_year", "year"),
        Index("ix_movies_is_read", "is_read"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    genres: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array as text
    torrent_url: Mapped[str] = mapped_column(
        String(1000), nullable=False, unique=True
    )
    qualities: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )  # JSON array
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rt_expert_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rt_audience_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    feed_entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enrichment_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class FeedHealth(Base):
    """Tracks the health/status of feed polling."""

    __tablename__ = "feed_health"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
