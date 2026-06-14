"""JSON API routes for pelis-feed web application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.common.models import Movie, FeedHealth
from src.webui.filters import filter_movies, group_by_year
from src.webui.enrichment import enrich_movie

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter()

_INDEX_HTML = Path(__file__).parent / "static" / "index.html"


def _get_session(request: Request) -> Session:
    """Dependency: get a database session from app state."""
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _get_config(request: Request) -> dict:
    """Dependency: get config from app state."""
    return request.app.state.config


def _movie_to_dict(movie: Movie) -> dict:
    """Convert a Movie ORM instance to a JSON-serializable dict."""
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


@router.get("/")
async def serve_index():
    """Serve the React frontend."""
    return FileResponse(str(_INDEX_HTML))


@router.get("/api/movies")
async def get_movies(
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Get filtered movie list grouped by year sections."""
    # Fetch all unread movies
    movies = session.query(Movie).filter(Movie.is_read == False).all()

    # Convert to dicts
    movie_dicts = [_movie_to_dict(m) for m in movies]

    # Apply config-driven filtering
    filtered = filter_movies(movie_dicts, config)

    # Group by year and sort by genre priority
    sections = group_by_year(filtered, config)

    total_count = sum(len(s["movies"]) for s in sections)

    return {"sections": sections, "total_count": total_count}


@router.post("/api/movies/{movie_id}/read")
async def mark_as_read(
    movie_id: int,
    session: Session = Depends(_get_session),
):
    """Mark a movie as read."""
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    movie.is_read = True
    movie.updated_at = datetime.now(timezone.utc)
    session.commit()

    return {
        "id": movie.id,
        "title": movie.title,
        "is_read": True,
        "updated_at": movie.updated_at.isoformat(),
    }


@router.post("/api/movies/{movie_id}/unread")
async def mark_as_unread(
    movie_id: int,
    session: Session = Depends(_get_session),
):
    """Mark a movie as unread."""
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    movie.is_read = False
    movie.updated_at = datetime.now(timezone.utc)
    session.commit()

    return {
        "id": movie.id,
        "title": movie.title,
        "is_read": False,
        "updated_at": movie.updated_at.isoformat(),
    }


@router.post("/api/movies/{movie_id}/enrich")
async def enrich(
    movie_id: int,
    session: Session = Depends(_get_session),
    config: dict = Depends(_get_config),
):
    """Trigger on-demand enrichment for a movie."""
    movie = session.query(Movie).filter(Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    # Call enrichment
    result = await enrich_movie(movie.title, movie.year, config)

    # Update movie record
    if result["imdb_rating"] is not None:
        movie.imdb_rating = result["imdb_rating"]
    if result["rt_expert_rating"] is not None:
        movie.rt_expert_rating = result["rt_expert_rating"]
    if result["rt_audience_rating"] is not None:
        movie.rt_audience_rating = result["rt_audience_rating"]

    movie.enrichment_date = result["enrichment_date"]
    movie.enrichment_error = result["enrichment_error"]
    movie.updated_at = datetime.now(timezone.utc)
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


@router.get("/api/health")
async def get_health(session: Session = Depends(_get_session)):
    """Get feed health status."""
    health = session.query(FeedHealth).first()

    if health is None:
        return {
            "last_success_at": None,
            "last_attempt_at": None,
            "last_error": None,
            "consecutive_failures": 0,
            "status": "unknown",
        }

    # Compute status
    now = datetime.now(timezone.utc)
    if health.last_success_at is None:
        status = "unknown"
    elif now - health.last_success_at > timedelta(hours=24):
        status = "degraded"
    else:
        status = "healthy"

    return {
        "last_success_at": health.last_success_at.isoformat() if health.last_success_at else None,
        "last_attempt_at": health.last_attempt_at.isoformat() if health.last_attempt_at else None,
        "last_error": health.last_error,
        "consecutive_failures": health.consecutive_failures,
        "status": status,
    }
