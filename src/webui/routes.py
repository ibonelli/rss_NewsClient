"""JSON API routes for pelis-feed web application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from collections import defaultdict

from src.common.models import AIFilteredView, FeedHealth, Filter, Movie, NewsItem, Series
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
        "imdb_id": movie.imdb_id,
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
    filtered: bool = Query(default=True),
):
    movies = session.query(Movie).filter(Movie.is_read == False).all()
    movie_dicts = [_movie_to_dict(m) for m in movies]
    if filtered:
        movie_dicts = filter_movies(movie_dicts, config)
    sections = group_by_year(movie_dicts, config)
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

    if result["imdb_id"] is not None:
        movie.imdb_id = result["imdb_id"]
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
        "imdb_id": movie.imdb_id,
        "imdb_rating": movie.imdb_rating,
        "rt_expert_rating": movie.rt_expert_rating,
        "rt_audience_rating": movie.rt_audience_rating,
        "enrichment_date": movie.enrichment_date.isoformat() if movie.enrichment_date else None,
        "enrichment_error": movie.enrichment_error,
    }


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

def _build_series_response(entries: list[Series]) -> list[dict]:
    by_title: dict[str, dict[int, list[Series]]] = defaultdict(lambda: defaultdict(list))
    for e in entries:
        by_title[e.title][e.season].append(e)

    result = []
    for title in sorted(by_title.keys()):
        seasons_map = by_title[title]
        all_eps = [ep for eps in seasons_map.values() for ep in eps]
        imdb_id = next((ep.imdb_id for ep in all_eps if ep.imdb_id), None)
        is_ignored = any(ep.is_ignored for ep in all_eps)
        seasons = [
            {
                "season": season_num,
                "episodes": [
                    {
                        "id": ep.id,
                        "episode": ep.episode,
                        "qualities": json.loads(ep.qualities) if ep.qualities else [],
                        "feed_entry_date": ep.feed_entry_date.isoformat() if ep.feed_entry_date else None,
                        "is_read": ep.is_read,
                        "is_ignored": ep.is_ignored,
                    }
                    for ep in sorted(seasons_map[season_num], key=lambda e: e.episode)
                ],
            }
            for season_num in sorted(seasons_map.keys())
        ]
        series_dict: dict = {
            "title": title,
            "imdb_id": imdb_id,
            "is_ignored": is_ignored,
            "seasons": seasons,
        }
        if imdb_id:
            series_dict["imdb_url"] = f"https://www.imdb.com/title/{imdb_id}/"
        result.append(series_dict)
    return result


@router.get("/api/series")
async def get_series(
    view: str = Query(default="filtered", pattern="^(filtered|all|read)$"),
    session: Session = Depends(_get_session),
):
    if view == "filtered":
        entries = (
            session.query(Series)
            .filter(Series.is_read == False, Series.is_ignored == False)
            .order_by(Series.title, Series.season, Series.episode)
            .all()
        )
        result = _build_series_response(entries)
    elif view == "all":
        entries = (
            session.query(Series)
            .filter(Series.is_read == False)
            .order_by(Series.title, Series.season, Series.episode)
            .all()
        )
        result = _build_series_response(entries)
    else:  # read
        entries = (
            session.query(Series)
            .filter(Series.is_read == True)
            .order_by(Series.title, Series.season, Series.episode)
            .all()
        )
        built = _build_series_response(entries)
        result = sorted(built, key=lambda s: (1 if s["is_ignored"] else 0, s["title"]))

    return {"series": result}


@router.post("/api/series/{series_id}/read")
async def mark_series_read(series_id: int, session: Session = Depends(_get_session)):
    entry = session.query(Series).filter(Series.id == series_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Series entry not found")
    entry.is_read = True
    entry.updated_at = datetime.utcnow()
    session.commit()
    return {"id": entry.id, "is_read": True}


@router.post("/api/series/{series_id}/unread")
async def mark_series_unread(series_id: int, session: Session = Depends(_get_session)):
    entry = session.query(Series).filter(Series.id == series_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Series entry not found")
    entry.is_read = False
    entry.updated_at = datetime.utcnow()
    session.commit()
    return {"id": entry.id, "is_read": False}


@router.post("/api/series/ignore")
async def ignore_series(
    payload: dict = Body(...),
    session: Session = Depends(_get_session),
):
    title = payload.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    count = session.query(Series).filter(Series.title == title).update(
        {"is_ignored": True, "updated_at": datetime.utcnow()}, synchronize_session=False
    )
    session.commit()
    return {"title": title, "is_ignored": True, "affected": count}


@router.post("/api/series/unignore")
async def unignore_series(
    payload: dict = Body(...),
    session: Session = Depends(_get_session),
):
    title = payload.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    count = session.query(Series).filter(Series.title == title).update(
        {"is_ignored": False, "updated_at": datetime.utcnow()}, synchronize_session=False
    )
    session.commit()
    return {"title": title, "is_ignored": False, "affected": count}


@router.post("/api/movies/read-all")
async def mark_all_movies_read(session: Session = Depends(_get_session)):
    count = session.query(Movie).filter(Movie.is_read == False).update(
        {"is_read": True, "updated_at": datetime.utcnow()}, synchronize_session=False
    )
    session.commit()
    return {"marked_read": count}


@router.post("/api/series/read-all")
async def mark_all_series_read(session: Session = Depends(_get_session)):
    count = session.query(Series).filter(Series.is_read == False).update(
        {"is_read": True, "updated_at": datetime.utcnow()}, synchronize_session=False
    )
    session.commit()
    return {"marked_read": count}


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
            session.query(AIFilteredView)
            .filter(AIFilteredView.feed_name == feed_name)
            .order_by(AIFilteredView.published_at.desc())
            .all()
        )
        items = [
            {
                "id": view.id,
                "source_item_id": view.source_item_id,
                "title": view.title,
                "url": view.url,
                "published_at": view.published_at.isoformat() if view.published_at else None,
                "category": view.category,
                "summary": view.summary,
                "tags": json.loads(view.tags) if view.tags else [],
                "is_read": view.is_read,
                "keep_as_context": view.keep_as_context,
                "ingested_at": view.ingested_at.isoformat() if view.ingested_at else None,
            }
            for view in rows
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
    # Gather which source_item_ids have an ai_filtered_views row
    view_ids = {
        row.source_item_id
        for row in session.query(AIFilteredView.source_item_id)
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


@router.post("/api/news/{feed_name}/read-all")
async def mark_all_news_read(
    feed_name: str,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    _get_news_feed_cfg(feed_name, config)
    session.query(NewsItem).filter(
        NewsItem.feed_name == feed_name, NewsItem.is_read == False
    ).update({"is_read": True}, synchronize_session=False)
    session.query(AIFilteredView).filter(
        AIFilteredView.feed_name == feed_name, AIFilteredView.is_read == False
    ).update({"is_read": True}, synchronize_session=False)
    session.commit()
    return {"ok": True}


@router.post("/api/news/views/{view_id}/unkeep")
async def unkeep_ai_view(view_id: int, session: Session = Depends(_get_session)):
    view = _get_ai_view(session, view_id)
    view.keep_as_context = False
    session.commit()
    return {"id": view.id, "keep_as_context": False}


# ---------------------------------------------------------------------------
# AI-filtered export / import (FR-033, FR-034)
# ---------------------------------------------------------------------------

def _get_news_feed_cfg(feed_name: str, config: dict) -> dict:
    news_feeds = config.get("news_feeds", [])
    feed_cfg = next((f for f in news_feeds if f.get("name") == feed_name), None)
    if feed_cfg is None:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed_cfg


@router.get("/api/news/{feed_name}/export")
async def export_feed(
    feed_name: str,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Return unread news_items + keep_as_context ai_filtered_views as a JSON download."""
    _get_news_feed_cfg(feed_name, config)

    unread_rows = (
        session.query(NewsItem)
        .filter(NewsItem.feed_name == feed_name, NewsItem.is_read == False)
        .order_by(NewsItem.published_at.desc())
        .all()
    )
    context_rows = (
        session.query(AIFilteredView)
        .filter(AIFilteredView.feed_name == feed_name, AIFilteredView.keep_as_context == True)
        .all()
    )

    payload = {
        "feed_name": feed_name,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "unread_items": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "content": r.full_content,
            }
            for r in unread_rows
        ],
        "context_items": [
            {
                "source_item_id": v.source_item_id,
                "title": v.title,
                "url": v.url,
                "published_at": v.published_at.isoformat() if v.published_at else None,
                "category": v.category,
                "summary": v.summary,
                "tags": json.loads(v.tags) if v.tags else [],
            }
            for v in context_rows
        ],
    }

    logger.info(
        "Export for '%s': %d unread items, %d context items",
        feed_name, len(unread_rows), len(context_rows),
    )

    safe_name = feed_name.replace(" ", "_").lower()
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-export.json"'},
    )


@router.post("/api/news/{feed_name}/import")
async def import_feed(
    feed_name: str,
    request: Request,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Replace all ai_filtered_views for the feed with the imported payload."""
    _get_news_feed_cfg(feed_name, config)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body is not valid JSON")

    views = body.get("views")
    if not isinstance(views, list):
        raise HTTPException(status_code=400, detail="Payload must have a 'views' array")

    # Build lookup of valid source_item_ids for this feed
    valid_ids = {
        row.id
        for row in session.query(NewsItem.id).filter(NewsItem.feed_name == feed_name).all()
    }

    now = datetime.utcnow()
    persisted = 0
    discarded = 0

    # Replace all existing rows for this feed
    session.query(AIFilteredView).filter(AIFilteredView.feed_name == feed_name).delete()

    for row in views:
        source_item_id = row.get("source_item_id")
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()

        if source_item_id not in valid_ids:
            logger.warning("Import for '%s': unknown source_item_id %s — discarding", feed_name, source_item_id)
            discarded += 1
            continue
        if not title or not url:
            logger.warning("Import for '%s': missing title or url for source_item_id %s — discarding", feed_name, source_item_id)
            discarded += 1
            continue

        category = (row.get("category") or "").strip()[:255] or None
        summary = (row.get("summary") or "").strip() or None
        tags = row.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        published_at = None
        if row.get("published_at"):
            try:
                published_at = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        session.add(AIFilteredView(
            source_item_id=source_item_id,
            feed_name=feed_name,
            title=title,
            url=url,
            published_at=published_at,
            category=category,
            summary=summary,
            tags=json.dumps(tags),
            is_read=False,
            keep_as_context=False,
            ingested_at=now,
        ))
        persisted += 1

    session.commit()
    logger.info(
        "Import for '%s': received %d rows, persisted %d, discarded %d",
        feed_name, len(views), persisted, discarded,
    )
    return {"imported": persisted, "discarded": discarded}
