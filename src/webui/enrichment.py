"""On-demand movie rating enrichment for pelis-feed.

Calls external free-tier APIs (OMDb) to fetch ratings for a specific movie.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

__all__ = ["enrich_movie"]

logger = logging.getLogger(__name__)


async def enrich_movie(movie_title: str, movie_year: int, config: dict) -> dict:
    """Fetch ratings for a movie from external APIs.

    Args:
        movie_title: Movie title to search for.
        movie_year: Movie release year.
        config: Application config dict (expects config["enrichment"]).

    Returns:
        Dict with keys: imdb_rating, rt_expert_rating, rt_audience_rating,
        enrichment_date, enrichment_error. Values are None if not found.
    """
    enrichment_config = config.get("enrichment", {})
    source = enrichment_config.get("source", "omdb")
    api_key = enrichment_config.get("api_key", "")
    timeout = enrichment_config.get("timeout_seconds", 10)

    result = {
        "imdb_rating": None,
        "rt_expert_rating": None,
        "rt_audience_rating": None,
        "enrichment_date": None,
        "enrichment_error": None,
    }

    if source == "omdb":
        return await _enrich_from_omdb(movie_title, movie_year, api_key, timeout, result)
    else:
        result["enrichment_error"] = f"Unknown enrichment source: {source}"
        logger.warning("Unknown enrichment source: %s", source)
        return result


async def _enrich_from_omdb(
    title: str, year: int, api_key: str, timeout: int, result: dict
) -> dict:
    """Fetch ratings from OMDb API (free tier).

    OMDb endpoint: http://www.omdbapi.com/?t={title}&y={year}&apikey={key}
    """
    if not api_key:
        result["enrichment_error"] = "No OMDb API key configured"
        logger.warning("OMDb enrichment skipped: no API key configured")
        return result

    url = "http://www.omdbapi.com/"
    params = {
        "t": title,
        "y": str(year),
        "apikey": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("Response") == "False":
            result["enrichment_error"] = data.get("Error", "Movie not found")
            logger.info("OMDb: movie not found — %s (%d)", title, year)
            return result

        # Extract IMDb rating
        imdb_str = data.get("imdbRating", "N/A")
        if imdb_str != "N/A":
            try:
                imdb_rating = float(imdb_str)
                if 0.0 <= imdb_rating <= 10.0:  # V-006
                    result["imdb_rating"] = imdb_rating
            except ValueError:
                pass

        # Extract Rotten Tomatoes ratings from Ratings array
        ratings = data.get("Ratings", [])
        for rating in ratings:
            source_name = rating.get("Source", "")
            value = rating.get("Value", "")

            if source_name == "Rotten Tomatoes" and value.endswith("%"):
                try:
                    rt_score = int(value.rstrip("%"))
                    if 0 <= rt_score <= 100:  # V-007
                        result["rt_expert_rating"] = rt_score
                except ValueError:
                    pass

        # OMDb doesn't typically provide RT audience score separately
        # but if available in Ratings, it would be "Rotten Tomatoes Audience"

        result["enrichment_date"] = datetime.now(timezone.utc)
        logger.info(
            "OMDb enrichment success for '%s' (%d): IMDb=%s, RT=%s",
            title,
            year,
            result["imdb_rating"],
            result["rt_expert_rating"],
        )

    except httpx.TimeoutException:
        result["enrichment_error"] = f"OMDb API timeout after {timeout}s"
        logger.warning("OMDb timeout for '%s' (%d)", title, year)
    except httpx.HTTPStatusError as e:
        result["enrichment_error"] = f"OMDb HTTP error: {e.response.status_code}"
        logger.warning("OMDb HTTP error for '%s': %s", title, e)
    except Exception as e:
        result["enrichment_error"] = f"Enrichment error: {str(e)}"
        logger.error("Unexpected enrichment error for '%s': %s", title, e)

    return result
