"""Deduplication logic for pelis-feed ingestion.

Handles merging movies that already exist in the database (by torrent URL or
by title+year match) and inserting new ones.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.common.models import Movie

__all__ = ["deduplicate_and_store"]

logger = logging.getLogger(__name__)


def _validate_movie(movie: dict) -> bool:
    """Validate a parsed movie dict against data contract rules V-001..V-005."""
    title = movie.get("title", "")
    if not title or not title.strip():
        logger.warning("V-001: Rejecting movie with empty title")
        return False

    year = movie.get("year", 0)
    if not (1900 <= year <= 2030):
        logger.warning("V-002: Rejecting movie with invalid year %d: %s", year, title)
        return False

    genres = movie.get("genres", [])
    if not isinstance(genres, list) or not genres:
        logger.warning("V-003: Rejecting movie with invalid genres: %s", title)
        return False

    torrent_url = movie.get("torrent_url", "")
    if not torrent_url or not torrent_url.strip():
        logger.warning("V-004: Rejecting movie with empty torrent_url: %s", title)
        return False

    qualities = movie.get("qualities", [])
    if not isinstance(qualities, list):
        logger.warning("V-005: Rejecting movie with invalid qualities: %s", title)
        return False

    return True


def _merge_qualities(existing_json: str, new_qualities: list[str]) -> str:
    """Merge new qualities into existing qualities JSON, returning updated JSON."""
    try:
        existing = json.loads(existing_json)
    except (json.JSONDecodeError, TypeError):
        existing = []

    merged = list(set(existing) | set(new_qualities))
    return json.dumps(sorted(merged))


def deduplicate_and_store(session: Session, movies: list[dict]) -> dict:
    """Deduplicate and store parsed movies in the database.

    For each movie:
    1. Check if torrent_url already exists → merge qualities
    2. Else check if title+year match exists → merge qualities
    3. Else insert as new record

    Args:
        session: SQLAlchemy session.
        movies: List of parsed movie dicts from the fetcher.

    Returns:
        Stats dict: {"inserted": N, "merged": N, "skipped": N}
    """
    stats = {"inserted": 0, "merged": 0, "skipped": 0}

    for movie in movies:
        if not _validate_movie(movie):
            stats["skipped"] += 1
            continue

        try:
            # V-009: Check for existing record with same torrent_url
            existing = session.query(Movie).filter(
                Movie.torrent_url == movie["torrent_url"]
            ).first()

            if existing:
                # V-010: Merge qualities
                existing.qualities = _merge_qualities(
                    existing.qualities, movie["qualities"]
                )
                existing.updated_at = datetime.now(timezone.utc)
                stats["merged"] += 1
                logger.debug("Merged qualities for existing URL: %s", movie["title"])
                continue

            # V-011: Check for same title + year
            existing = session.query(Movie).filter(
                Movie.title == movie["title"],
                Movie.year == movie["year"],
            ).first()

            if existing:
                existing.qualities = _merge_qualities(
                    existing.qualities, movie["qualities"]
                )
                existing.updated_at = datetime.now(timezone.utc)
                stats["merged"] += 1
                logger.debug("Merged qualities for title+year match: %s (%d)", movie["title"], movie["year"])
                continue

            # Insert new movie
            new_movie = Movie(
                title=movie["title"],
                year=movie["year"],
                genres=json.dumps(movie["genres"]),
                torrent_url=movie["torrent_url"],
                qualities=json.dumps(movie["qualities"]),
                imdb_rating=movie.get("imdb_rating"),
                poster_url=movie.get("poster_url"),
                feed_entry_date=movie["feed_entry_date"],
                is_read=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_movie)
            stats["inserted"] += 1
            logger.debug("Inserted new movie: %s (%d)", movie["title"], movie["year"])

        except Exception as e:
            logger.error("Error processing movie '%s': %s", movie.get("title", "?"), e)
            stats["skipped"] += 1

    session.commit()
    return stats
