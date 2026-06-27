"""Deduplication logic for pelis-feed ingestion.

Handles merging movies that already exist in the database (by torrent URL or
by title+year match) and inserting new ones.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from src.common.models import Movie, Series, SeriesEpisode

__all__ = ["deduplicate_and_store", "deduplicate_and_store_series"]

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
                existing.updated_at = datetime.utcnow()
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
                existing.updated_at = datetime.utcnow()
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
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(new_movie)
            stats["inserted"] += 1
            logger.debug("Inserted new movie: %s (%d)", movie["title"], movie["year"])

        except Exception as e:
            logger.error("Error processing movie '%s': %s", movie.get("title", "?"), e)
            stats["skipped"] += 1

    session.commit()
    return stats


def _merge_series_qualities(existing_json: str, new_variant: dict) -> str:
    """Merge a new quality variant into the existing qualities JSON (union by quality name)."""
    try:
        existing = json.loads(existing_json)
    except (json.JSONDecodeError, TypeError):
        existing = []

    known = {v["quality"] for v in existing if isinstance(v, dict) and "quality" in v}
    if new_variant["quality"] not in known:
        existing.append(new_variant)

    return json.dumps(existing)


def deduplicate_and_store_series(session: Session, entries: list[dict]) -> dict:
    """Deduplicate and store series entries using the two-table design.

    Level 1 (V-025a): upsert series title row in `series`.
    Level 2 (V-025b): upsert episode row in `series_episodes` by (series_id, season, episode).
    is_ignored lives on the `series` row — new episodes for an ignored series automatically
    inherit that status via JOIN at query time, requiring no per-episode flag.

    Args:
        session: SQLAlchemy session.
        entries: List of parsed series dicts from the fetcher.

    Returns:
        Stats dict: {"inserted": N, "merged": N, "skipped": N}
    """
    stats = {"inserted": 0, "merged": 0, "skipped": 0}

    for entry in entries:
        title = (entry.get("title") or "").strip()
        season = entry.get("season")
        episode = entry.get("episode")
        quality = entry.get("quality", "unknown")
        torrent_page_url = (entry.get("torrent_page_url") or "").strip()

        if not title:  # V-021
            logger.warning("V-021: Skipping series entry with empty title")
            stats["skipped"] += 1
            continue
        if not isinstance(season, int) or season < 0:  # V-022
            logger.warning("V-022: Skipping series entry with invalid season: %s", entry)
            stats["skipped"] += 1
            continue
        if not isinstance(episode, int) or episode < 0:  # V-023
            logger.warning("V-023: Skipping series entry with invalid episode: %s", entry)
            stats["skipped"] += 1
            continue
        if not torrent_page_url:  # V-024
            logger.warning("V-024: Skipping series entry with no torrent URL: %s", title)
            stats["skipped"] += 1
            continue

        new_variant = {"quality": quality, "torrent_page_url": torrent_page_url}

        try:
            # Level 1: upsert series title row (V-025a)
            series_row = session.query(Series).filter(Series.title == title).first()
            if not series_row:
                series_row = Series(
                    title=title,
                    imdb_id=entry.get("imdb_id"),
                    is_ignored=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(series_row)
                session.flush()  # populate series_row.id before inserting episode

            # Level 2: upsert episode row (V-025b)
            ep_row = (
                session.query(SeriesEpisode)
                .filter(
                    SeriesEpisode.series_id == series_row.id,
                    SeriesEpisode.season == season,
                    SeriesEpisode.episode == episode,
                )
                .first()
            )

            if ep_row:
                ep_row.qualities = _merge_series_qualities(ep_row.qualities, new_variant)
                ep_row.updated_at = datetime.utcnow()
                stats["merged"] += 1
                logger.debug("Merged quality '%s' for '%s' S%02dE%02d", quality, title, season, episode)
            else:
                session.add(SeriesEpisode(
                    series_id=series_row.id,
                    season=season,
                    episode=episode,
                    qualities=json.dumps([new_variant]),
                    feed_entry_date=entry.get("feed_entry_date"),
                    ingested_at=datetime.utcnow(),
                    is_read=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                ))
                stats["inserted"] += 1
                logger.debug("Inserted '%s' S%02dE%02d (%s)", title, season, episode, quality)

        except Exception as e:
            logger.error("Error processing series entry '%s' S%02dE%02d: %s", title, season, episode, e)
            stats["skipped"] += 1

    session.commit()
    return stats
