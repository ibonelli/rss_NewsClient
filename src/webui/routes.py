"""JSON API routes for pelis-feed web application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.common.models import AIFilteredView, Category, FeedHealth, Filter, Movie, NewsItem
from src.webui.filters import filter_movies, group_by_year
from src.webui.enrichment import enrich_movie

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter()

_INDEX_HTML = Path(__file__).parent / "static" / "index.html"


def _get_session(request: Request) -> Session:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _get_config(request: Request) -> dict:
    return request.app.state.config


def _movie_to_dict(movie: Movie) -> dict:
    return {
        "id": movie.id,
        "title": movie.title,
        "year": movie.year,
        "genres": json.loads(movie.genres) if movie.genres else [],
        "qualities": json.loads(movie.qualities) if movie.qualities else [],
        "torrent_url": movie.torrent_url,
        "imdb_rating": movie.imdb_rating,
        "rt_expert_rating": movie.rt_expert_rating,
        "rt_audience_rating": movie.rt_audience_rating,
        "poster_url": movie.poster_url,
        "feed_entry_date": movie.feed_entry_date.isoformat() if movie.feed_entry_date else None,
        "enrichment_date": movie.enrichment_date.isoformat() if movie.enrichment_date else None,
        "enrichment_error": movie.enrichment_error,
        "is_read": movie.is_read,
    }


def _health_status(health: FeedHealth, now: datetime) -> str:
    if health.last_success_at is None:
        return "unknown"
    if now - health.last_success_at > timedelta(hours=24):
        return "degraded"
    return "healthy"


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@router.get("/")
async def serve_index():
    return FileResponse(str(_INDEX_HTML))


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------

@router.get("/api/movies")
async def get_movies(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    movies = session.query(Movie).filter(Movie.is_read == False).all()
    movie_dicts = [_movie_to_dict(m) for m in movies]
    filtered = filter_movies(movie_dicts, config)
    sections = group_by_year(filtered, config)
    return {"sections": sections, "total_count": sum(len(s["movies"]) for s in sections)}


@router.post("/api/movies/{movie_id}/read")
async def mark_movie_read(movie_id: int, session: Session = Depends(_get_session)):
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    movie.is_read = True
    movie.updated_at = datetime.utcnow()
    session.commit()
    return {"id": movie.id, "title": movie.title, "is_read": True, "updated_at": movie.updated_at.isoformat()}


@router.post("/api/movies/{movie_id}/unread")
async def mark_movie_unread(movie_id: int, session: Session = Depends(_get_session)):
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    movie.is_read = False
    movie.updated_at = datetime.utcnow()
    session.commit()
    return {"id": movie.id, "title": movie.title, "is_read": False, "updated_at": movie.updated_at.isoformat()}


@router.post("/api/movies/{movie_id}/enrich")
async def enrich(
    movie_id: int,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    result = await enrich_movie(movie.title, movie.year, config)

    if result["imdb_rating"] is not None:
        movie.imdb_rating = result["imdb_rating"]
    if result["rt_expert_rating"] is not None:
        movie.rt_expert_rating = result["rt_expert_rating"]
    if result["rt_audience_rating"] is not None:
        movie.rt_audience_rating = result["rt_audience_rating"]
    movie.enrichment_date = result["enrichment_date"]
    movie.enrichment_error = result["enrichment_error"]
    movie.updated_at = datetime.utcnow()
    session.commit()

    return {
        "id": movie.id,
        "title": movie.title,
        "imdb_rating": movie.imdb_rating,
        "rt_expert_rating": movie.rt_expert_rating,
        "rt_audience_rating": movie.rt_audience_rating,
        "enrichment_date": movie.enrichment_date.isoformat() if movie.enrichment_date else None,
        "enrichment_error": movie.enrichment_error,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/api/health")
async def get_health(session: Session = Depends(_get_session)):
    all_health = session.query(FeedHealth).all()
    now = datetime.utcnow()

    if not all_health:
        return {"feeds": []}

    return {
        "feeds": [
            {
                "feed_name": h.feed_name,
                "last_success_at": h.last_success_at.isoformat() if h.last_success_at else None,
                "last_attempt_at": h.last_attempt_at.isoformat() if h.last_attempt_at else None,
                "last_error": h.last_error,
                "consecutive_failures": h.consecutive_failures,
                "status": _health_status(h, now),
            }
            for h in all_health
        ]
    }


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

@router.get("/api/news")
async def get_news_feeds(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """List all configured news feeds with type and unread counts."""
    news_feeds = config.get("news_feeds", [])
    result = []
    for feed_cfg in news_feeds:
        feed_name = feed_cfg.get("name", "")
        feed_type = feed_cfg.get("type", "unfiltered")
        if not feed_name:
            continue

        if feed_type == "ai_filtered":
            unread = (
                session.query(AIFilteredView)
                .filter(AIFilteredView.feed_name == feed_name, AIFilteredView.is_read == False)
                .count()
            )
        elif feed_type == "filtered":
            unread = (
                session.query(NewsItem)
                .filter(
                    NewsItem.feed_name == feed_name,
                    NewsItem.is_read == False,
                    NewsItem.matched_filter_id != None,
                )
                .count()
            )
        else:
            unread = (
                session.query(NewsItem)
                .filter(NewsItem.feed_name == feed_name, NewsItem.is_read == False)
                .count()
            )

        result.append({"name": feed_name, "type": feed_type, "unread_count": unread})

    return {"feeds": result}


@router.get("/api/news/{feed_name}/items")
async def get_news_items(
    feed_name: str,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Return news items for a feed, shaped by feed type."""
    news_feeds = config.get("news_feeds", [])
    feed_cfg = next((f for f in news_feeds if f.get("name") == feed_name), None)
    if feed_cfg is None:
        raise HTTPException(status_code=404, detail="Feed not found")

    feed_type = feed_cfg.get("type", "unfiltered")

    if feed_type == "unfiltered":
        rows = (
            session.query(NewsItem)
            .filter(NewsItem.feed_name == feed_name)
            .order_by(NewsItem.published_at.desc())
            .all()
        )
        items = [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                "is_read": r.is_read,
            }
            for r in rows
        ]

    elif feed_type == "filtered":
        # Load filter name lookup
        filters = {f.id: f.name for f in session.query(Filter).filter(Filter.feed_name == feed_name).all()}
        rows = (
            session.query(NewsItem)
            .filter(NewsItem.feed_name == feed_name, NewsItem.matched_filter_id != None)
            .order_by(NewsItem.published_at.desc())
            .all()
        )
        items = [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
                "is_read": r.is_read,
                "matched_filter_name": filters.get(r.matched_filter_id, ""),
            }
            for r in rows
        ]

    else:  # ai_filtered
        rows = (
            session.query(AIFilteredView, NewsItem, Category)
            .join(NewsItem, AIFilteredView.news_item_id == NewsItem.id)
            .outerjoin(Category, AIFilteredView.category_id == Category.id)
            .filter(AIFilteredView.feed_name == feed_name)
            .order_by(NewsItem.published_at.desc())
            .all()
        )
        items = [
            {
                "id": view.id,
                "news_item_id": view.news_item_id,
                "title": news_item.title,
                "url": news_item.url,
                "published_at": news_item.published_at.isoformat() if news_item.published_at else None,
                "category": cat.name if cat else None,
                "summary": view.summary,
                "tags": json.loads(view.tags) if view.tags else [],
                "is_read": view.is_read,
                "keep_as_context": view.keep_as_context,
                "last_filtered_at": view.last_filtered_at.isoformat() if view.last_filtered_at else None,
            }
            for view, news_item, cat in rows
        ]

    return {"feed_name": feed_name, "type": feed_type, "items": items}


@router.get("/api/news/{feed_name}/raw")
async def get_news_raw(
    feed_name: str,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Return raw news_items for an AI-filtered feed (FR-032 sub-view)."""
    news_feeds = config.get("news_feeds", [])
    feed_cfg = next((f for f in news_feeds if f.get("name") == feed_name), None)
    if feed_cfg is None:
        raise HTTPException(status_code=404, detail="Feed not found")
    if feed_cfg.get("type") != "ai_filtered":
        raise HTTPException(status_code=400, detail="Raw view only available for ai_filtered feeds")

    # Gather which news_item_ids have an ai_filtered_views row
    view_ids = {
        row.news_item_id
        for row in session.query(AIFilteredView.news_item_id)
        .filter(AIFilteredView.feed_name == feed_name)
        .all()
    }

    rows = (
        session.query(NewsItem)
        .filter(NewsItem.feed_name == feed_name)
        .order_by(NewsItem.published_at.desc())
        .all()
    )
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "full_content": r.full_content,
            "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
            "is_read": r.is_read,
            "has_ai_view": r.id in view_ids,
        }
        for r in rows
    ]
    return {"feed_name": feed_name, "items": items}


# ---------------------------------------------------------------------------
# News read tracking — news_items
# ---------------------------------------------------------------------------

def _get_news_item(session: Session, item_id: int) -> NewsItem:
    item = session.query(NewsItem).filter(NewsItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")
    return item


@router.post("/api/news/items/{item_id}/read")
async def mark_news_item_read(item_id: int, session: Session = Depends(_get_session)):
    item = _get_news_item(session, item_id)
    item.is_read = True
    session.commit()
    return {"id": item.id, "is_read": True}


@router.post("/api/news/items/{item_id}/unread")
async def mark_news_item_unread(item_id: int, session: Session = Depends(_get_session)):
    item = _get_news_item(session, item_id)
    item.is_read = False
    session.commit()
    return {"id": item.id, "is_read": False}


# ---------------------------------------------------------------------------
# News read tracking — ai_filtered_views
# ---------------------------------------------------------------------------

def _get_ai_view(session: Session, view_id: int) -> AIFilteredView:
    view = session.query(AIFilteredView).filter(AIFilteredView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="AI filtered view not found")
    return view


@router.post("/api/news/views/{view_id}/read")
async def mark_ai_view_read(view_id: int, session: Session = Depends(_get_session)):
    view = _get_ai_view(session, view_id)
    view.is_read = True
    session.commit()
    return {"id": view.id, "is_read": True}


@router.post("/api/news/views/{view_id}/unread")
async def mark_ai_view_unread(view_id: int, session: Session = Depends(_get_session)):
    view = _get_ai_view(session, view_id)
    view.is_read = False
    session.commit()
    return {"id": view.id, "is_read": False}


@router.post("/api/news/views/{view_id}/keep")
async def keep_ai_view(view_id: int, session: Session = Depends(_get_session)):
    view = _get_ai_view(session, view_id)
    view.keep_as_context = True
    session.commit()
    return {"id": view.id, "keep_as_context": True}


@router.post("/api/news/views/{view_id}/unkeep")
async def unkeep_ai_view(view_id: int, session: Session = Depends(_get_session)):
    view = _get_ai_view(session, view_id)
    view.keep_as_context = False
    session.commit()
    return {"id": view.id, "keep_as_context": False}
