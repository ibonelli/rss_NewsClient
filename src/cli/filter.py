"""CLI Filter Processor — regex and AI filtering for news items.

Run from the project root after the ingester:
    python src/cli/filter.py

Cron entry: python src/cli/main.py && python src/cli/filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import logging
import re
import subprocess
from datetime import datetime

from sqlalchemy.orm import Session

from src.common.config import load_config
from src.common.db import get_engine, get_session_factory, init_db
from src.common.models import AIFilteredView, Category, Filter, NewsItem


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
    """Match unmatched news_items for a filtered feed against all its filter patterns."""
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
                logger.warning("Invalid regex pattern '%s' in filter '%s': %s", f.pattern, f.name, e)

    session.commit()
    logger.info("Regex pass for '%s': matched %d items", feed_name, matched_count)


def _get_or_create_category(session: Session, name: str) -> int:
    """Get or create a Category row by name, returning its id."""
    name = name.strip()[:255]
    cat = session.query(Category).filter(Category.name == name).first()
    if cat is None:
        cat = Category(name=name)
        session.add(cat)
        session.flush()
    return cat.id


def _run_ai_pass(
    session: Session, feed_cfg: dict, logger: logging.Logger
) -> None:
    """Invoke Claude CLI for an AI-filtered feed and upsert ai_filtered_views."""
    feed_name = feed_cfg.get("name", "")
    claude_prompt = feed_cfg.get("claude_prompt", "").strip()
    timeout = int(feed_cfg.get("claude_timeout_seconds", 60))

    # Pending: never processed OR ai_filtered_views.is_read = false (re-evaluate)
    processed_ids = {
        row.news_item_id
        for row in session.query(AIFilteredView.news_item_id)
        .filter(AIFilteredView.feed_name == feed_name, AIFilteredView.is_read == True)
        .all()
    }
    pending_items = (
        session.query(NewsItem)
        .filter(
            NewsItem.feed_name == feed_name,
            ~NewsItem.id.in_(processed_ids) if processed_ids else True,
        )
        .all()
    )

    if not pending_items:
        logger.info("AI pass for '%s': no pending items", feed_name)
        return

    # Context: keep_as_context = true rows (with joined news_item data)
    context_rows = (
        session.query(AIFilteredView, NewsItem, Category)
        .join(NewsItem, AIFilteredView.news_item_id == NewsItem.id)
        .outerjoin(Category, AIFilteredView.category_id == Category.id)
        .filter(AIFilteredView.feed_name == feed_name, AIFilteredView.keep_as_context == True)
        .all()
    )

    pending_payload = [
        {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "content": item.full_content,
        }
        for item in pending_items
    ]

    context_payload = [
        {
            "id": view.news_item_id,
            "title": news_item.title,
            "category": cat.name if cat else "",
            "summary": view.summary or "",
            "tags": json.loads(view.tags) if view.tags else [],
        }
        for view, news_item, cat in context_rows
    ]

    prompt = (
        f"{claude_prompt}\n\n"
        "Evaluate the news items below. Return ONLY a JSON array of items worth surfacing. "
        "Do not include context items in your output. Items you omit will not appear in the filtered view. "
        "Respond with valid JSON only — no markdown, no explanation.\n\n"
        "=== PENDING ITEMS (evaluate these) ===\n"
        f"{json.dumps(pending_payload, ensure_ascii=False)}\n\n"
        "=== CONTEXT ITEMS (reference only — do not include in output) ===\n"
        f"{json.dumps(context_payload, ensure_ascii=False)}"
    )

    logger.info(
        "AI pass for '%s': sending %d items, %d context items to Claude",
        feed_name, len(pending_payload), len(context_payload),
    )

    try:
        result = subprocess.run(
            ["claude", "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.error("AI pass for '%s': 'claude' CLI not found — skipping", feed_name)
        return
    except subprocess.TimeoutExpired:
        logger.error(
            "AI pass for '%s': Claude CLI timed out after %ds — skipping", feed_name, timeout
        )
        return

    if result.returncode != 0:
        logger.error(
            "AI pass for '%s': Claude CLI exited with code %d: %s",
            feed_name, result.returncode, result.stderr[:500],
        )
        return

    raw_output = result.stdout.strip()
    try:
        claude_items = json.loads(raw_output)
        if not isinstance(claude_items, list):
            raise ValueError("Expected a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(
            "AI pass for '%s': invalid JSON from Claude: %s — output: %.200s",
            feed_name, e, raw_output,
        )
        return

    pending_ids = {item.id for item in pending_items}
    upserted = 0

    for claude_item in claude_items:
        item_id = claude_item.get("id")
        if item_id not in pending_ids:
            logger.warning("AI pass for '%s': unknown id %s in Claude output — discarding", feed_name, item_id)
            continue

        category_str = (claude_item.get("category") or "").strip()
        summary = (claude_item.get("summary") or "").strip()
        tags = claude_item.get("tags", [])

        if not category_str:
            logger.warning("AI pass for '%s': missing category for item %s — skipping", feed_name, item_id)
            continue
        if not isinstance(tags, list):
            tags = []

        category_id = _get_or_create_category(session, category_str)

        existing_view = (
            session.query(AIFilteredView)
            .filter(AIFilteredView.news_item_id == item_id)
            .first()
        )
        if existing_view:
            # Update AI fields only — never overwrite is_read or keep_as_context (V-020)
            existing_view.category_id = category_id
            existing_view.summary = summary
            existing_view.tags = json.dumps(tags)
            existing_view.last_filtered_at = datetime.utcnow()
        else:
            session.add(AIFilteredView(
                news_item_id=item_id,
                feed_name=feed_name,
                category_id=category_id,
                summary=summary,
                tags=json.dumps(tags),
                is_read=False,
                keep_as_context=False,
                last_filtered_at=datetime.utcnow(),
            ))
        upserted += 1

    session.commit()
    logger.info(
        "AI pass for '%s': Claude returned %d items, upserted %d",
        feed_name, len(claude_items), upserted,
    )


def main() -> None:
    """Run the filter processor: sync filters, regex pass, AI pass."""
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

    # Sync filters table from config
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

        elif feed_type == "ai_filtered":
            with SessionFactory() as session:
                _run_ai_pass(session, feed_cfg, logger)

    logger.info("Filter processor run complete")


if __name__ == "__main__":
    main()
