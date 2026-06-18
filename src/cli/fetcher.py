"""RSS feed fetcher and parser for pelis-feed.

Fetches the YTS RSS feed and extracts movie entries with title, year,
genres, quality, torrent URL, poster, and any ratings available in the feed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html.parser import HTMLParser

import feedparser

__all__ = ["fetch_feed"]

logger = logging.getLogger(__name__)

# Regex patterns for parsing YTS RSS title format
# Examples: "Movie Title (2024) [1080p] [WEBRip]", "Movie Title (2024) [720p]"
_TITLE_PATTERN = re.compile(
    r"^(.+?)\s*\((\d{4})\)\s*(?:\[([^\]]+)\])?"
)
_QUALITY_PATTERN = re.compile(r"\[(\d{3,4}p)\]")
_YEAR_PATTERN = re.compile(r"\((\d{4})\)")


class _DescriptionParser(HTMLParser):
    """Simple HTML parser to extract info from RSS <description> field."""

    def __init__(self):
        super().__init__()
        self.poster_url: str | None = None
        self.genres: list[str] = []
        self.imdb_rating: float | None = None
        self._current_data: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            for name, value in attrs:
                if name == "src" and value:
                    self.poster_url = value
                    break

    def handle_data(self, data: str) -> None:
        self._current_data.append(data)

    def extract_metadata(self) -> None:
        """Parse collected text data for genres and ratings."""
        full_text = " ".join(self._current_data)

        # Look for genre info (YTS often has "Genre: Action / Thriller")
        genre_match = re.search(r"Genre:\s*(.+?)(?:\n|$|Rating:)", full_text, re.IGNORECASE)
        if genre_match:
            raw_genres = genre_match.group(1)
            self.genres = [g.strip() for g in re.split(r"[/,]", raw_genres) if g.strip()]

        # Look for IMDB rating (e.g., "Rating: 7.2" or "IMDB: 7.2")
        rating_match = re.search(r"(?:Rating|IMDB):\s*(\d+\.?\d*)", full_text, re.IGNORECASE)
        if rating_match:
            try:
                rating = float(rating_match.group(1))
                if 0.0 <= rating <= 10.0:
                    self.imdb_rating = rating
            except ValueError:
                pass


def _parse_description(description: str) -> dict:
    """Parse the RSS description HTML for poster, genres, and ratings."""
    parser = _DescriptionParser()
    try:
        parser.feed(description or "")
        parser.extract_metadata()
    except Exception:
        logger.debug("Failed to parse description HTML")

    return {
        "poster_url": parser.poster_url,
        "genres": parser.genres,
        "imdb_rating": parser.imdb_rating,
    }


def _parse_entry(entry: dict) -> dict | None:
    """Parse a single feedparser entry into a movie dict.

    Returns None if the entry cannot be parsed.
    """
    raw_title = entry.get("title", "")
    if not raw_title.strip():
        logger.warning("Skipping entry with empty title")
        return None

    # Extract title, year, qualities from the title string
    title_match = _TITLE_PATTERN.match(raw_title)
    if title_match:
        title = title_match.group(1).strip()
        year = int(title_match.group(2))
    else:
        # Fallback: try to find year anywhere in title
        year_match = _YEAR_PATTERN.search(raw_title)
        if year_match:
            year = int(year_match.group(1))
            title = raw_title[: year_match.start()].strip()
        else:
            title = raw_title.strip()
            year = datetime.utcnow().year
            logger.warning("No year found in title: %s, defaulting to current year", raw_title)

    # Extract qualities like [720p], [1080p], [2160p]
    qualities = _QUALITY_PATTERN.findall(raw_title)
    if not qualities:
        qualities = ["Unknown"]

    # Get torrent URL from link or enclosure
    torrent_url = ""
    if entry.get("enclosures"):
        torrent_url = entry["enclosures"][0].get("href", "")
    if not torrent_url:
        torrent_url = entry.get("link", "")
    if not torrent_url:
        logger.warning("Skipping entry with no URL: %s", raw_title)
        return None

    # Parse description HTML
    description = entry.get("summary", "") or entry.get("description", "")
    desc_data = _parse_description(description)

    # Parse publication date
    published = entry.get("published_parsed")
    if published:
        try:
            feed_entry_date = datetime(*published[:6])
        except (TypeError, ValueError):
            feed_entry_date = datetime.utcnow()
    else:
        feed_entry_date = datetime.utcnow()

    genres = desc_data["genres"] if desc_data["genres"] else ["Unknown"]

    return {
        "title": title,
        "year": year,
        "genres": genres,
        "torrent_url": torrent_url,
        "qualities": qualities,
        "poster_url": desc_data["poster_url"],
        "imdb_rating": desc_data["imdb_rating"],
        "feed_entry_date": feed_entry_date,
    }


def fetch_feed(feed_url: str) -> list[dict]:
    """Fetch and parse the YTS RSS feed, returning a list of movie dicts."""
    logger.info("Fetching RSS feed from: %s", feed_url)

    feed = feedparser.parse(feed_url)

    if feed.bozo:
        logger.warning("Feed parsing had issues: %s", feed.bozo_exception)

    if not feed.entries:
        logger.warning("No entries found in feed")
        return []

    logger.info("Found %d entries in feed", len(feed.entries))

    movies = []
    for entry in feed.entries:
        try:
            parsed = _parse_entry(entry)
            if parsed:
                movies.append(parsed)
        except Exception as e:
            logger.warning("Failed to parse entry: %s — %s", entry.get("title", "?"), e)

    logger.info("Successfully parsed %d movies from feed", len(movies))
    return movies


def fetch_news_feed(feed_name: str, feed_url: str) -> list[dict]:
    """Fetch and parse a news RSS/Atom feed, returning a list of news item dicts.

    Args:
        feed_name: Logical name of the feed (from config).
        feed_url: URL of the RSS/Atom feed.

    Returns:
        List of news item dicts with keys: feed_name, title, url, published_at,
        full_content. Unparseable entries are logged and skipped.

    Raises:
        Exception: On network failure (caller should catch and record in feed_health).
    """
    logger.info("Fetching news feed '%s' from: %s", feed_name, feed_url)

    feed = feedparser.parse(feed_url)

    if feed.bozo:
        logger.warning("News feed '%s' parsing had issues: %s", feed_name, feed.bozo_exception)

    if not feed.entries:
        logger.info("No entries found in news feed '%s'", feed_name)
        return []

    logger.info("Found %d entries in news feed '%s'", len(feed.entries), feed_name)

    items = []
    for entry in feed.entries:
        try:
            parsed = _parse_news_entry(feed_name, entry)
            if parsed:
                items.append(parsed)
        except Exception as e:
            logger.warning(
                "Failed to parse news entry in '%s': %s — %s",
                feed_name, entry.get("title", "?"), e,
            )

    logger.info("Parsed %d news items from feed '%s'", len(items), feed_name)
    return items


def _parse_news_entry(feed_name: str, entry: dict) -> dict | None:
    """Parse a single feedparser entry into a news item dict."""
    title = (entry.get("title") or "").strip()
    if not title:
        logger.debug("Skipping news entry with empty title in feed '%s'", feed_name)
        return None

    url = entry.get("link", "").strip()
    if not url:
        logger.debug("Skipping news entry with no URL: %s", title)
        return None

    # feedparser normalises RSS pubDate and Atom updated/published into published_parsed
    published_at = None
    if entry.get("published_parsed"):
        try:
            published_at = datetime(*entry["published_parsed"][:6])
        except (TypeError, ValueError):
            pass
    elif entry.get("updated_parsed"):
        try:
            published_at = datetime(*entry["updated_parsed"][:6])
        except (TypeError, ValueError):
            pass

    # Prefer full content over summary; feedparser puts Atom <content> in entry.content list
    full_content = ""
    if entry.get("content"):
        full_content = entry["content"][0].get("value", "")
    if not full_content:
        full_content = entry.get("summary", "") or ""

    return {
        "feed_name": feed_name,
        "title": title,
        "url": url,
        "published_at": published_at,
        "full_content": full_content,
    }
