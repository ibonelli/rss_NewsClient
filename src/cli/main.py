"""CLI Ingester — fetches all feeds, stores raw data, updates feed health.

Run from the project root:
    python src/cli/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.common.config import load_config
from src.common.db import get_engine, get_session_factory, init_db
from src.common.models import DesignItem, NewsItem
from src.cli.fetcher import fetch_feed, fetch_series_feed, fetch_news_feed, fetch_design_feed
from src.cli.dedup import deduplicate_and_store, deduplicate_and_store_series
from src.cli.alerter import update_feed_health, check_and_alert

_MOVIE_FEED_NAME = "yts_movies"
_SERIES_FEED_NAME = "eztv_series"


def _store_news_items(session: Session, items: list[dict]) -> dict:
    """Store news items, skipping duplicates by (url, feed_name).

    Returns:
        Stats dict: {"inserted": N, "skipped": N}
    """
    stats = {"inserted": 0, "skipped": 0}

    for item in items:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        feed_name = item.get("feed_name", "")

        if not title or not url or not feed_name:
            stats["skipped"] += 1
            continue

        existing = (
            session.query(NewsItem)
            .filter(NewsItem.url == url, NewsItem.feed_name == feed_name)
            .first()
        )
        if existing:
            stats["skipped"] += 1
            continue

        news_item = NewsItem(
            feed_name=feed_name,
            title=title,
            url=url,
            published_at=item.get("published_at"),
            full_content=item.get("full_content") or "",
            ingested_at=datetime.utcnow(),
            is_read=False,
        )
        session.add(news_item)
        stats["inserted"] += 1

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Re-insert one by one to skip real duplicates on race condition
        for item in items:
            try:
                session.add(NewsItem(
                    feed_name=item.get("feed_name", ""),
                    title=(item.get("title") or "").strip(),
                    url=(item.get("url") or "").strip(),
                    published_at=item.get("published_at"),
                    full_content=item.get("full_content") or "",
                    ingested_at=datetime.utcnow(),
                    is_read=False,
                ))
                session.commit()
            except IntegrityError:
                session.rollback()

    return stats


def _store_design_items(session: Session, items: list[dict]) -> dict:
    """Store design items, skipping duplicates by (url, feed_name)."""
    stats = {"inserted": 0, "skipped": 0}

    for item in items:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        feed_name = item.get("feed_name", "")

        if not title or not url or not feed_name:
            stats["skipped"] += 1
            continue

        existing = (
            session.query(DesignItem)
            .filter(DesignItem.url == url, DesignItem.feed_name == feed_name)
            .first()
        )
        if existing:
            stats["skipped"] += 1
            continue

        session.add(DesignItem(
            feed_name=feed_name,
            title=title,
            url=url,
            published_at=item.get("published_at"),
            summary=item.get("summary") or "",
            image_url=item.get("image_url"),
            ingested_at=datetime.utcnow(),
            is_read=False,
        ))
        stats["inserted"] += 1

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        for item in items:
            try:
                session.add(DesignItem(
                    feed_name=item.get("feed_name", ""),
                    title=(item.get("title") or "").strip(),
                    url=(item.get("url") or "").strip(),
                    published_at=item.get("published_at"),
                    summary=item.get("summary") or "",
                    image_url=item.get("image_url"),
                    ingested_at=datetime.utcnow(),
                    is_read=False,
                ))
                session.commit()
            except IntegrityError:
                session.rollback()

    return stats


def main() -> None:
    """Run the full ingestion pipeline: movie feed then all news feeds."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ingester] %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting pelis-feed ingester")

    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    engine = get_engine(config)
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    # --- Movie feed ---
    feed_url = config.get("feed", {}).get("url", "")
    if not feed_url:
        logger.error("No movie feed URL configured (feed.url)")
        sys.exit(1)

    movie_success = False
    movie_error = None
    try:
        movies = fetch_feed(feed_url)
        movie_success = True
    except Exception as e:
        movie_error = str(e)
        logger.error("Failed to fetch movie feed: %s", e)
        movies = []

    if movies:
        with SessionFactory() as session:
            stats = deduplicate_and_store(session, movies)
            logger.info(
                "Movies: %d inserted, %d merged, %d skipped",
                stats["inserted"], stats["merged"], stats["skipped"],
            )

    with SessionFactory() as session:
        update_feed_health(session, _MOVIE_FEED_NAME, success=movie_success, error=movie_error)

    # --- Series feed ---
    series_feed_url = config.get("series_feed", {}).get("url", "")
    if series_feed_url:
        series_success = False
        series_error = None
        try:
            series_entries = fetch_series_feed(series_feed_url)
            series_success = True
        except Exception as e:
            series_error = str(e)
            logger.error("Failed to fetch series feed: %s", e)
            series_entries = []

        if series_entries:
            with SessionFactory() as session:
                stats = deduplicate_and_store_series(session, series_entries)
                logger.info(
                    "Series: %d inserted, %d merged, %d skipped",
                    stats["inserted"], stats["merged"], stats["skipped"],
                )

        with SessionFactory() as session:
            update_feed_health(session, _SERIES_FEED_NAME, success=series_success, error=series_error)
    else:
        logger.info("No series feed URL configured — skipping series ingestion")

    # --- News feeds ---
    news_feeds = config.get("news_feeds", [])
    for feed_cfg in news_feeds:
        feed_name = feed_cfg.get("name", "")
        feed_url_news = feed_cfg.get("url", "")
        if not feed_name or not feed_url_news:
            logger.warning("Skipping news feed with missing name or url: %s", feed_cfg)
            continue

        news_success = False
        news_error = None
        try:
            items = fetch_news_feed(feed_name, feed_url_news)
            news_success = True
        except Exception as e:
            news_error = str(e)
            logger.error("Failed to fetch news feed '%s': %s", feed_name, e)
            items = []

        if items:
            with SessionFactory() as session:
                stats = _store_news_items(session, items)
                logger.info(
                    "News feed '%s': %d inserted, %d skipped",
                    feed_name, stats["inserted"], stats["skipped"],
                )

        with SessionFactory() as session:
            update_feed_health(session, feed_name, success=news_success, error=news_error)

    # --- Design feeds ---
    design_feeds = config.get("design_feeds", [])
    for feed_cfg in design_feeds:
        feed_name = feed_cfg.get("name", "")
        feed_url_design = feed_cfg.get("url", "")
        if not feed_name or not feed_url_design:
            logger.warning("Skipping design feed with missing name or url: %s", feed_cfg)
            continue

        design_success = False
        design_error = None
        try:
            items = fetch_design_feed(feed_name, feed_url_design)
            design_success = True
        except Exception as e:
            design_error = str(e)
            logger.error("Failed to fetch design feed '%s': %s", feed_name, e)
            items = []

        if items:
            with SessionFactory() as session:
                stats = _store_design_items(session, items)
                logger.info(
                    "Design feed '%s': %d inserted, %d skipped",
                    feed_name, stats["inserted"], stats["skipped"],
                )

        with SessionFactory() as session:
            update_feed_health(session, feed_name, success=design_success, error=design_error)

    # --- Alert check (all feeds) ---
    with SessionFactory() as session:
        alerted = check_and_alert(session, config)
        if alerted:
            logger.info("Feed downtime alert sent for %d feed(s)", alerted)

    logger.info("Ingester run complete")


if __name__ == "__main__":
    main()
