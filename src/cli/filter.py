"""CLI Filter Processor — regex flagging for news items.

Syncs the filters table from config and sets matched_filter_id on matching
news_items for 'filtered' feeds. Never deletes rows. AI-filtered feeds are
handled externally via the web UI export/import workflow (ADR-009).

Run from the project root after the ingester:
    python src/cli/filter.py

Cron entry:
    python src/cli/main.py && python src/cli/filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import logging
import re

from sqlalchemy.orm import Session

from src.common.config import load_config
from src.common.db import get_engine, get_session_factory, init_db
from src.common.models import Filter, NewsItem


def _sync_filters(session: Session, news_feeds: list[dict]) -> None:
    """Upsert Filter rows from config for all filtered feeds."""
    for feed_cfg in news_feeds:
        if feed_cfg.get("type") != "filtered":
            continue
        feed_name = feed_cfg.get("name", "")
        for f in feed_cfg.get("filters", []):
            name = f.get("name", "")
            pattern = f.get("pattern", "")
            if not name or not pattern:
                continue
            existing = (
                session.query(Filter)
                .filter(Filter.feed_name == feed_name, Filter.name == name)
                .first()
            )
            if existing:
                existing.pattern = pattern
            else:
                session.add(Filter(feed_name=feed_name, name=name, pattern=pattern))
    session.commit()


def _run_regex_pass(session: Session, feed_name: str, logger: logging.Logger) -> None:
    """Match unmatched news_items for a filtered feed against all its filter patterns.

    Sets matched_filter_id on items that match. Items that do not match are left
    with matched_filter_id = null — they remain in the DB but are hidden from the
    filtered UI view. No rows are deleted.
    """
    filters = session.query(Filter).filter(Filter.feed_name == feed_name).all()
    if not filters:
        logger.warning("No filters configured for filtered feed '%s'", feed_name)
        return

    unmatched = (
        session.query(NewsItem)
        .filter(NewsItem.feed_name == feed_name, NewsItem.matched_filter_id == None)
        .all()
    )
    logger.info("Regex pass for '%s': checking %d unmatched items", feed_name, len(unmatched))

    matched_count = 0
    for item in unmatched:
        text = f"{item.title} {item.full_content}"
        for f in filters:
            try:
                if re.search(f.pattern, text, re.IGNORECASE):
                    item.matched_filter_id = f.id
                    matched_count += 1
                    break
            except re.error as e:
                logger.warning(
                    "Invalid regex pattern '%s' in filter '%s': %s", f.pattern, f.name, e
                )

    session.commit()
    logger.info("Regex pass for '%s': matched %d items", feed_name, matched_count)


def main() -> None:
    """Run the filter processor: sync filters then regex-flag matching items."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [filter] %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting pelis-feed filter processor")

    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    engine = get_engine(config)
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    news_feeds = config.get("news_feeds", [])
    if not news_feeds:
        logger.info("No news_feeds configured — nothing to do")
        return

    with SessionFactory() as session:
        _sync_filters(session, news_feeds)

    for feed_cfg in news_feeds:
        feed_type = feed_cfg.get("type", "unfiltered")
        feed_name = feed_cfg.get("name", "")
        if not feed_name:
            continue

        if feed_type == "filtered":
            with SessionFactory() as session:
                _run_regex_pass(session, feed_name, logger)
        elif feed_type not in ("filtered", "unfiltered"):
            logger.warning("Feed '%s' has unknown type %r — skipping", feed_name, feed_type)

    logger.info("Filter processor run complete")


if __name__ == "__main__":
    main()
