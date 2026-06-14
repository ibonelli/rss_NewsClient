"""CLI Ingester — fetches RSS, parses, deduplicates, stores, checks health.

Entry point for the ingestion process. Run from the project root:
    python src/cli/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import logging

from src.common.config import load_config
from src.common.db import get_engine, get_session_factory, init_db
from src.cli.fetcher import fetch_feed
from src.cli.dedup import deduplicate_and_store
from src.cli.alerter import update_feed_health, check_and_alert


def main() -> None:
    """Run the full ingestion pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ingester] %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting pelis-feed ingester")

    # Load configuration
    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # Initialize database
    engine = get_engine(config)
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    # Fetch RSS feed
    feed_url = config.get("feed", {}).get("url", "")
    if not feed_url:
        logger.error("No feed URL configured (feed.url)")
        sys.exit(1)

    success = False
    error_msg = None

    try:
        movies = fetch_feed(feed_url)
        success = True
    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to fetch feed: %s", e)
        movies = []

    # Deduplicate and store
    if movies:
        with SessionFactory() as session:
            stats = deduplicate_and_store(session, movies)
            logger.info(
                "Dedup results: %d inserted, %d merged, %d skipped",
                stats["inserted"],
                stats["merged"],
                stats["skipped"],
            )

    # Update feed health
    with SessionFactory() as session:
        update_feed_health(session, success=success, error=error_msg)

    # Check alert threshold
    with SessionFactory() as session:
        alert_sent = check_and_alert(session, config)
        if alert_sent:
            logger.info("Feed downtime alert email sent")

    logger.info("Ingester run complete")


if __name__ == "__main__":
    main()
