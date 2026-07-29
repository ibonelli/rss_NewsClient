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

from src.common.models import DesignItem, FeedHealth, Filter, Movie, NewsItem, SavedEntry, Series, SeriesEpisode
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


def _movie_to_dict(movie: Movie, saved_ids: set[int] | None = None) -> dict:
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
        "is_saved": movie.id in (saved_ids or set()),
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
# News is tag-scoped (ADR-016): /news/{tag} and /news/{tag}/{feed_name}. Design is
# unchanged: /design/{feed_name}. `tag`/`feed_name` are accepted but unused server-side.
@router.get("/movies")
@router.get("/series")
@router.get("/news")
@router.get("/news/{tag}")
@router.get("/news/{tag}/{feed_name}")
@router.get("/design")
@router.get("/design/{feed_name}")
@router.get("/saved")
async def serve_spa_route(tag: str | None = None, feed_name: str | None = None):
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
    saved_ids = _saved_source_ids(session, "movie")
    movie_dicts = [_movie_to_dict(m, saved_ids) for m in movies]

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


@router.post("/api/movies/{movie_id}/save")
async def save_movie(movie_id: int, session: Session = Depends(_get_session)):
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    entry = _get_or_create_saved_entry(session, "movie", movie.id, _movie_save_fields(movie))
    return _saved_entry_to_dict(entry)


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

_SERIES_CATEGORIES = {"inbox", "ongoing", "following", "ignored"}


def _earliest_season_episode_by_series(session: Session, series_ids: list[int]) -> dict[int, tuple[int, int]]:
    """Map each series_id to the (season, episode) of its earliest-ingested episode.

    Season-0 specials are excluded (FR-088) — "earliest" means the lowest `id`
    (insertion order) among episodes with season >= 1. A series with no such
    episode yet is simply absent from the returned map.
    """
    if not series_ids:
        return {}
    rows = (
        session.query(SeriesEpisode.series_id, SeriesEpisode.season, SeriesEpisode.episode)
        .filter(SeriesEpisode.series_id.in_(series_ids), SeriesEpisode.season >= 1)
        .order_by(SeriesEpisode.series_id, SeriesEpisode.id.asc())
        .all()
    )
    earliest: dict[int, tuple[int, int]] = {}
    for series_id, season, episode in rows:
        earliest.setdefault(series_id, (season, episode))
    return earliest


def _series_category_filter(session: Session, category: str):
    """Build the SQLAlchemy filter expression for a series category.

    Following/Ignored are stored booleans. Inbox/OnGoing split the untriaged
    bucket (is_following=False, is_ignored=False) by each series' earliest
    ingested episode (FR-088) — computed at query time, never stored, mirroring
    the Movie Flagged/Un-Flagged pattern.
    """
    if category not in _SERIES_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category: {category!r}")
    if category == "following":
        return and_(Series.is_following == True, Series.is_ignored == False)
    if category == "ignored":
        return Series.is_ignored == True

    untriaged_ids = [
        sid for (sid,) in session.query(Series.id)
        .filter(Series.is_following == False, Series.is_ignored == False)
        .all()
    ]
    earliest = _earliest_season_episode_by_series(session, untriaged_ids)
    inbox_ids = [sid for sid in untriaged_ids if earliest.get(sid) == (1, 1)]
    if category == "inbox":
        return Series.id.in_(inbox_ids)
    inbox_id_set = set(inbox_ids)
    ongoing_ids = [sid for sid in untriaged_ids if sid not in inbox_id_set]
    return Series.id.in_(ongoing_ids)


def _get_series_or_404(session: Session, series_id: int) -> Series:
    row = session.query(Series).filter(Series.id == series_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Series not found")
    return row


def _series_imdb_url(series: Series) -> str:
    if series.imdb_id:
        return f"https://www.imdb.com/title/{series.imdb_id}/"
    return f"https://www.imdb.com/search/title/?title={quote_plus(series.title)}&title_type=tv_series"


def _build_series_response(results: list, saved_ids: set[int] | None = None) -> list[dict]:
    """Build the series API response from (Series, SeriesEpisode) join tuples."""
    saved_ids = saved_ids or set()
    by_series: dict[int, dict] = {}
    for series, ep in results:
        if series.id not in by_series:
            by_series[series.id] = {
                "id": series.id,
                "title": series.title,
                "imdb_id": series.imdb_id,
                "imdb_url": _series_imdb_url(series),
                "is_following": series.is_following,
                "is_ignored": series.is_ignored,
                "is_saved": series.id in saved_ids,
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
    cat_filter = _series_category_filter(session, category)
    rows = (
        session.query(Series, SeriesEpisode)
        .join(SeriesEpisode, SeriesEpisode.series_id == Series.id)
        .filter(cat_filter, SeriesEpisode.is_read == read)
        .order_by(Series.title, SeriesEpisode.season, SeriesEpisode.episode)
        .all()
    )
    saved_ids = _saved_source_ids(session, "series")
    return {"read": read, "category": category, "series": _build_series_response(rows, saved_ids)}


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


@router.post("/api/series/{series_id}/save")
async def save_series(series_id: int, session: Session = Depends(_get_session)):
    row = _get_series_or_404(session, series_id)
    entry = _get_or_create_saved_entry(session, "series", row.id, _series_save_fields(row))
    return _saved_entry_to_dict(entry)


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
    cat_filter = _series_category_filter(session, category)
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
    if category not in ("inbox", "ongoing", "following"):
        raise HTTPException(status_code=422, detail="category must be 'inbox', 'ongoing', or 'following'")
    cat_filter = _series_category_filter(session, category)
    count = session.query(Series).filter(cat_filter).update(
        {"is_ignored": True, "is_following": False}, synchronize_session=False
    )
    session.commit()
    return {"ignored": count}


# ---------------------------------------------------------------------------
# Saved entries — shared helpers (ADR-017)
# ---------------------------------------------------------------------------

def _movie_imdb_url(title: str, year: int, imdb_id: str | None) -> str:
    """Mirrors the client-side imdbUrl computation in app.js's MovieCard —
    kept in sync manually since movies have no server-side IMDb URL field."""
    if imdb_id:
        return f"https://www.imdb.com/title/{imdb_id}/"
    return f"https://www.imdb.com/find/?q={quote_plus(title + ' ' + str(year))}&s=tt&ttype=ft"


def _movie_save_fields(movie: Movie) -> dict:
    return {
        "title": movie.title,
        "link": _movie_imdb_url(movie.title, movie.year, movie.imdb_id),
        "entry_date": movie.feed_entry_date,
        "feed_name": "Movies",
        "summary": movie.plot or "",
    }


def _series_save_fields(series: Series) -> dict:
    return {
        "title": series.title,
        "link": _series_imdb_url(series),
        "entry_date": series.created_at,
        "feed_name": "Series",
        "summary": "",
    }


def _news_save_fields(item: NewsItem) -> dict:
    return {
        "title": item.title,
        "link": item.url,
        "entry_date": item.published_at,
        "feed_name": item.feed_name,
        "summary": item.full_content,
    }


def _design_save_fields(item: DesignItem) -> dict:
    return {
        "title": item.title,
        "link": item.url,
        "entry_date": item.published_at,
        "feed_name": item.feed_name,
        "summary": item.summary,
    }


def _get_or_create_saved_entry(session: Session, source_type: str, source_id: int, fields: dict) -> SavedEntry:
    """Idempotent on (source_type, source_id) — FR-097/V-043: re-saving an
    already-saved item returns the existing row unchanged, never a duplicate
    or an update of the existing snapshot."""
    existing = (
        session.query(SavedEntry)
        .filter(SavedEntry.source_type == source_type, SavedEntry.source_id == source_id)
        .first()
    )
    if existing:
        return existing
    entry = SavedEntry(source_type=source_type, source_id=source_id, **fields)
    session.add(entry)
    session.commit()
    return entry


def _saved_entry_to_dict(entry: SavedEntry) -> dict:
    return {
        "id": entry.id,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "title": entry.title,
        "link": entry.link,
        "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
        "feed_name": entry.feed_name,
        "summary": entry.summary,
        "saved_at": entry.saved_at.isoformat() if entry.saved_at else None,
    }


def _saved_source_ids(session: Session, source_type: str) -> set[int]:
    """The set of source_ids already saved for a given source_type — one query
    per list request, avoiding an is_saved N+1 lookup per item (FR-098)."""
    return {
        sid for (sid,) in session.query(SavedEntry.source_id)
        .filter(SavedEntry.source_type == source_type).all()
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
    """List all configured news feeds with type, tag, and unread counts.

    Feeds are returned pre-sorted into tag-priority order (news_tag_priority,
    FR-091) so the client can group this array by `tag` without needing the
    raw priority list itself.
    """
    news_feeds = config.get("news_feeds", [])
    result = []
    for feed_cfg in news_feeds:
        feed_name = feed_cfg.get("name", "")
        feed_type = feed_cfg.get("type", "unfiltered")
        feed_tag = feed_cfg.get("tag") or "General"
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

        result.append({"name": feed_name, "type": feed_type, "tag": feed_tag, "unread_count": unread})

    tag_order = {tag: i for i, tag in enumerate(config.get("news_tag_priority", []))}
    next_index = len(tag_order)
    for feed in result:
        if feed["tag"] not in tag_order:
            tag_order[feed["tag"]] = next_index
            next_index += 1
    result.sort(key=lambda feed: tag_order[feed["tag"]])

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
    saved_ids = _saved_source_ids(session, "news")

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
                "is_saved": r.id in saved_ids,
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
                "is_saved": r.id in saved_ids,
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


@router.post("/api/news/items/{item_id}/save")
async def save_news_item(item_id: int, session: Session = Depends(_get_session)):
    item = _get_news_item(session, item_id)
    entry = _get_or_create_saved_entry(session, "news", item.id, _news_save_fields(item))
    return _saved_entry_to_dict(entry)


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
    saved_ids = _saved_source_ids(session, "design")
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "summary": r.summary,
            "image_url": r.image_url,
            "is_read": r.is_read,
            "is_saved": r.id in saved_ids,
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


@router.post("/api/design/items/{item_id}/save")
async def save_design_item(item_id: int, session: Session = Depends(_get_session)):
    item = session.query(DesignItem).filter(DesignItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Design item not found")
    entry = _get_or_create_saved_entry(session, "design", item.id, _design_save_fields(item))
    return _saved_entry_to_dict(entry)


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


# ---------------------------------------------------------------------------
# Saved (ADR-017)
# ---------------------------------------------------------------------------

@router.get("/api/saved")
async def get_saved(session: Session = Depends(_get_session)):
    entries = session.query(SavedEntry).order_by(SavedEntry.saved_at.desc()).all()
    return {"entries": [_saved_entry_to_dict(e) for e in entries], "total_count": len(entries)}


@router.delete("/api/saved/{entry_id}")
async def delete_saved(entry_id: int, session: Session = Depends(_get_session)):
    entry = session.query(SavedEntry).filter(SavedEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Saved entry not found")
    session.delete(entry)
    session.commit()
    return {"ok": True}


@router.get("/api/saved/export")
async def export_saved(session: Session = Depends(_get_session)):
    """Return every saved_entries row as a JSON download — no read/unread
    filtering applies (Saved has no read state), unlike the unread-only
    News export (FR-102)."""
    entries = session.query(SavedEntry).order_by(SavedEntry.saved_at.desc()).all()

    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "entries": [_saved_entry_to_dict(e) for e in entries],
    }

    logger.info("Saved export: %d items", len(entries))

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="saved-export.json"'},
    )
