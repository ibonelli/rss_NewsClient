"""JSON API routes for pelis-feed web application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from collections import defaultdict

from src.common.models import DesignItem, FeedHealth, Filter, Movie, NewsItem, Series, SeriesEpisode
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
        "runtime": movie.runtime,
        "plot": movie.plot,
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


# Bookmarkable/shareable per-feed-type URLs. The SPA reads the path client-side
# (see parseLocation() in app.js) to pick the active tab and, for news/design,
# the active sub-feed — the server just needs to return the same shell for all of them.
@router.get("/movies")
@router.get("/series")
@router.get("/news")
@router.get("/news/{feed_name}")
@router.get("/design")
@router.get("/design/{feed_name}")
async def serve_spa_route(feed_name: str | None = None):
    return FileResponse(str(_INDEX_HTML))


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------

@router.get("/api/movies")
async def get_movies(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
    read: bool = Query(default=False),
    flagged: bool = Query(default=True),
):
    movies = session.query(Movie).filter(Movie.is_read == read).all()
    movie_dicts = [_movie_to_dict(m) for m in movies]

    flagged_dicts = filter_movies(movie_dicts, config)
    if flagged:
        result_dicts = flagged_dicts
    else:
        flagged_ids = {m["id"] for m in flagged_dicts}
        result_dicts = [m for m in movie_dicts if m["id"] not in flagged_ids]

    sections = group_by_year(result_dicts, config)
    return {"read": read, "flagged": flagged, "sections": sections, "total_count": sum(len(s["movies"]) for s in sections)}


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

_SERIES_CATEGORIES = {"inbox", "following", "ignored"}


def _series_category_filter(category: str):
    """Build the SQLAlchemy filter expression for a series category.

    Category is derived from two independent booleans rather than stored
    directly (see Series model): inbox = both false (default, untriaged),
    following = is_following true, ignored = is_ignored true.
    """
    if category not in _SERIES_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category: {category!r}")
    if category == "inbox":
        return and_(Series.is_following == False, Series.is_ignored == False)
    if category == "following":
        return and_(Series.is_following == True, Series.is_ignored == False)
    return Series.is_ignored == True


def _get_series_or_404(session: Session, series_id: int) -> Series:
    row = session.query(Series).filter(Series.id == series_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Series not found")
    return row


def _build_series_response(results: list) -> list[dict]:
    """Build the series API response from (Series, SeriesEpisode) join tuples."""
    by_series: dict[int, dict] = {}
    for series, ep in results:
        if series.id not in by_series:
            imdb_url = (
                f"https://www.imdb.com/title/{series.imdb_id}/"
                if series.imdb_id
                else f"https://www.imdb.com/search/title/?title={quote_plus(series.title)}&title_type=tv_series"
            )
            by_series[series.id] = {
                "id": series.id,
                "title": series.title,
                "imdb_id": series.imdb_id,
                "imdb_url": imdb_url,
                "is_following": series.is_following,
                "is_ignored": series.is_ignored,
                "seasons": defaultdict(list),
            }
        by_series[series.id]["seasons"][ep.season].append(ep)

    result = []
    for series_id in sorted(by_series.keys(), key=lambda sid: by_series[sid]["title"]):
        data = by_series[series_id]
        seasons_map = data.pop("seasons")
        data["seasons"] = [
            {
                "season": season_num,
                "episodes": [
                    {
                        "id": ep.id,
                        "episode": ep.episode,
                        "qualities": json.loads(ep.qualities) if ep.qualities else [],
                        "feed_entry_date": ep.feed_entry_date.isoformat() if ep.feed_entry_date else None,
                        "is_read": ep.is_read,
                    }
                    for ep in sorted(seasons_map[season_num], key=lambda e: e.episode)
                ],
            }
            for season_num in sorted(seasons_map.keys())
        ]
        result.append(data)
    return result


@router.get("/api/series")
async def get_series(
    read: bool = Query(default=False),
    category: str = Query(default="following"),
    session: Session = Depends(_get_session),
):
    cat_filter = _series_category_filter(category)
    rows = (
        session.query(Series, SeriesEpisode)
        .join(SeriesEpisode, SeriesEpisode.series_id == Series.id)
        .filter(cat_filter, SeriesEpisode.is_read == read)
        .order_by(Series.title, SeriesEpisode.season, SeriesEpisode.episode)
        .all()
    )
    return {"read": read, "category": category, "series": _build_series_response(rows)}


@router.post("/api/series/{series_id}/follow")
async def follow_series(series_id: int, session: Session = Depends(_get_session)):
    row = _get_series_or_404(session, series_id)
    row.is_following = True
    row.is_ignored = False
    row.updated_at = datetime.utcnow()
    session.commit()
    return {"id": row.id, "title": row.title, "is_following": True, "is_ignored": False}


@router.post("/api/series/{series_id}/unfollow")
async def unfollow_series(series_id: int, session: Session = Depends(_get_session)):
    row = _get_series_or_404(session, series_id)
    row.is_following = False
    row.updated_at = datetime.utcnow()
    session.commit()
    return {"id": row.id, "title": row.title, "is_following": False, "is_ignored": row.is_ignored}


@router.post("/api/series/{series_id}/ignore")
async def ignore_series(series_id: int, session: Session = Depends(_get_session)):
    row = _get_series_or_404(session, series_id)
    row.is_ignored = True
    row.is_following = False
    row.updated_at = datetime.utcnow()
    session.commit()
    return {"id": row.id, "title": row.title, "is_following": False, "is_ignored": True}


@router.post("/api/series/{series_id}/unignore")
async def unignore_series(series_id: int, session: Session = Depends(_get_session)):
    row = _get_series_or_404(session, series_id)
    row.is_ignored = False
    row.updated_at = datetime.utcnow()
    session.commit()
    return {"id": row.id, "title": row.title, "is_following": row.is_following, "is_ignored": False}


@router.post("/api/series/episodes/{episode_id}/read")
async def mark_episode_read(episode_id: int, session: Session = Depends(_get_session)):
    ep = session.query(SeriesEpisode).filter(SeriesEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    ep.is_read = True
    ep.updated_at = datetime.utcnow()
    session.commit()
    return {"id": ep.id, "is_read": True}


@router.post("/api/series/episodes/{episode_id}/unread")
async def mark_episode_unread(episode_id: int, session: Session = Depends(_get_session)):
    ep = session.query(SeriesEpisode).filter(SeriesEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    ep.is_read = False
    ep.updated_at = datetime.utcnow()
    session.commit()
    return {"id": ep.id, "is_read": False}


@router.post("/api/movies/read-all")
async def mark_all_movies_read(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
    flagged: bool = Query(default=True),
):
    unread_movies = session.query(Movie).filter(Movie.is_read == False).all()
    movie_dicts = [_movie_to_dict(m) for m in unread_movies]
    flagged_dicts = filter_movies(movie_dicts, config)
    if flagged:
        target_ids = {m["id"] for m in flagged_dicts}
    else:
        flagged_ids = {m["id"] for m in flagged_dicts}
        target_ids = {m["id"] for m in movie_dicts if m["id"] not in flagged_ids}
    count = 0
    for movie in unread_movies:
        if movie.id in target_ids:
            movie.is_read = True
            movie.updated_at = datetime.utcnow()
            count += 1
    session.commit()
    return {"marked_read": count}


@router.post("/api/series/read-all")
async def mark_all_series_read(
    session: Session = Depends(_get_session),
    category: str = Query(default="following"),
):
    cat_filter = _series_category_filter(category)
    series_ids = [s.id for s in session.query(Series).filter(cat_filter).all()]
    count = session.query(SeriesEpisode).filter(
        SeriesEpisode.series_id.in_(series_ids),
        SeriesEpisode.is_read == False,
    ).update({"is_read": True, "updated_at": datetime.utcnow()}, synchronize_session=False)
    session.commit()
    return {"marked_read": count}


@router.post("/api/series/ignore-all")
async def ignore_all_series(
    session: Session = Depends(_get_session),
    category: str = Query(default="following"),
):
    if category not in ("inbox", "following"):
        raise HTTPException(status_code=422, detail="category must be 'inbox' or 'following'")
    cat_filter = _series_category_filter(category)
    count = session.query(Series).filter(cat_filter).update(
        {"is_ignored": True, "is_following": False}, synchronize_session=False
    )
    session.commit()
    return {"ignored": count}


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

        if feed_type == "filtered":
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
    read: bool = Query(default=False),
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Return news items for a feed filtered by read state, shaped by feed type."""
    news_feeds = config.get("news_feeds", [])
    feed_cfg = next((f for f in news_feeds if f.get("name") == feed_name), None)
    if feed_cfg is None:
        raise HTTPException(status_code=404, detail="Feed not found")

    feed_type = feed_cfg.get("type", "unfiltered")

    if feed_type == "unfiltered":
        rows = (
            session.query(NewsItem)
            .filter(NewsItem.feed_name == feed_name, NewsItem.is_read == read)
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
        filters = {f.id: f.name for f in session.query(Filter).filter(Filter.feed_name == feed_name).all()}
        rows = (
            session.query(NewsItem)
            .filter(
                NewsItem.feed_name == feed_name,
                NewsItem.matched_filter_id != None,
                NewsItem.is_read == read,
            )
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

    else:
        raise HTTPException(status_code=422, detail=f"Unsupported feed type: {feed_type!r}")

    return {"feed_name": feed_name, "type": feed_type, "read": read, "items": items}


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
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# News export (FR-033)
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
    """Return unread news_items as a JSON download (always exports unread regardless of UI toggle)."""
    _get_news_feed_cfg(feed_name, config)

    unread_rows = (
        session.query(NewsItem)
        .filter(NewsItem.feed_name == feed_name, NewsItem.is_read == False)
        .order_by(NewsItem.published_at.desc())
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
    }

    logger.info("Export for '%s': %d unread items", feed_name, len(unread_rows))

    safe_name = feed_name.replace(" ", "_").lower()
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-export.json"'},
    )


# ---------------------------------------------------------------------------
# Design feeds
# ---------------------------------------------------------------------------

def _get_design_feed_cfg(feed_name: str, config: dict) -> dict:
    design_feeds = config.get("design_feeds", [])
    feed_cfg = next((f for f in design_feeds if f.get("name") == feed_name), None)
    if feed_cfg is None:
        raise HTTPException(status_code=404, detail="Design feed not found")
    return feed_cfg


@router.get("/api/design")
async def get_design_feeds(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    design_feeds = config.get("design_feeds", [])
    result = []
    for feed_cfg in design_feeds:
        feed_name = feed_cfg.get("name", "")
        if not feed_name:
            continue
        unread = (
            session.query(DesignItem)
            .filter(DesignItem.feed_name == feed_name, DesignItem.is_read == False)
            .count()
        )
        result.append({"name": feed_name, "unread_count": unread})
    return {"feeds": result}


@router.get("/api/design/{feed_name}/items")
async def get_design_items(
    feed_name: str,
    read: bool = Query(default=False),
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    _get_design_feed_cfg(feed_name, config)
    rows = (
        session.query(DesignItem)
        .filter(DesignItem.feed_name == feed_name, DesignItem.is_read == read)
        .order_by(DesignItem.published_at.desc())
        .all()
    )
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "summary": r.summary,
            "image_url": r.image_url,
            "is_read": r.is_read,
        }
        for r in rows
    ]
    return {"feed_name": feed_name, "read": read, "items": items}


@router.post("/api/design/items/{item_id}/read")
async def mark_design_item_read(item_id: int, session: Session = Depends(_get_session)):
    item = session.query(DesignItem).filter(DesignItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Design item not found")
    item.is_read = True
    session.commit()
    return {"id": item.id, "is_read": True}


@router.post("/api/design/items/{item_id}/unread")
async def mark_design_item_unread(item_id: int, session: Session = Depends(_get_session)):
    item = session.query(DesignItem).filter(DesignItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Design item not found")
    item.is_read = False
    session.commit()
    return {"id": item.id, "is_read": False}


@router.post("/api/design/{feed_name}/read-all")
async def mark_all_design_read(
    feed_name: str,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    _get_design_feed_cfg(feed_name, config)
    count = session.query(DesignItem).filter(
        DesignItem.feed_name == feed_name, DesignItem.is_read == False
    ).update({"is_read": True}, synchronize_session=False)
    session.commit()
    return {"marked_read": count}
