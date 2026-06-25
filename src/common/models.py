"""SQLAlchemy 2.0 declarative models for pelis-feed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "Movie", "Series", "FeedHealth", "NewsItem", "Filter", "AIFilteredView"]


class Base(DeclarativeBase):
    pass


class Movie(Base):
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
    torrent_url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    qualities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rt_expert_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rt_audience_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    feed_entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enrichment_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        Index("ix_series_title_season_episode", "title", "season", "episode", unique=True),
        Index("ix_series_title", "title"),
        Index("ix_series_is_read", "is_read"),
        Index("ix_series_is_ignored", "is_ignored"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    imdb_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    qualities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON: [{quality, torrent_page_url}]
    feed_entry_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class FeedHealth(Base):
    """One row per configured feed (movie feed + each news feed)."""

    __tablename__ = "feed_health"
    __table_args__ = (
        Index("ix_feed_health_feed_name", "feed_name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # server_default ensures existing rows get 'yts_movies' on ALTER TABLE ADD COLUMN
    feed_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="yts_movies")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NewsItem(Base):
    """A raw news item fetched from any news feed type."""

    __tablename__ = "news_items"
    __table_args__ = (
        Index("ix_news_items_url_feed", "url", "feed_name", unique=True),
        Index("ix_news_items_feed_name", "feed_name"),
        Index("ix_news_items_is_read", "is_read"),
        Index("ix_news_items_matched_filter_id", "matched_filter_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    full_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matched_filter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("filters.id"), nullable=True
    )


class Filter(Base):
    """A named regex pattern for a filtered news feed, synced from config."""

    __tablename__ = "filters"
    __table_args__ = (
        Index("ix_filters_feed_name_name", "feed_name", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AIFilteredView(Base):
    """An AI-processed news item imported via the export/import workflow."""

    __tablename__ = "ai_filtered_views"
    __table_args__ = (
        Index("ix_ai_filtered_views_source_item_id", "source_item_id", unique=True),
        Index("ix_ai_filtered_views_feed_name", "feed_name"),
        Index("ix_ai_filtered_views_is_read", "is_read"),
        Index("ix_ai_filtered_views_keep_as_context", "keep_as_context"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_items.id"), nullable=False)
    feed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array as text
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    keep_as_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
