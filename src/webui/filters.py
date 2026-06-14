"""Filtering and sorting logic for pelis-feed movie display.

Applies config-driven rating thresholds, groups by year sections,
and sorts by genre priority.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

__all__ = ["filter_movies", "group_by_year", "sort_by_genre_priority"]


def filter_movies(movies: list[dict], config: dict) -> list[dict]:
    """Filter movies based on config-driven rating thresholds.

    Movies with NO ratings (all null) always pass — they haven't been enriched yet.
    Movies WITH ratings must meet genre-specific or default thresholds.
    Older movies use stricter thresholds.

    Args:
        movies: List of movie dicts (already serialized from DB).
        config: Application config dict.

    Returns:
        Filtered list of movies that pass the thresholds.
    """
    filtering = config.get("filtering", {})
    defaults = filtering.get("default", {})
    genre_overrides = filtering.get("genres", {})
    older_config = filtering.get("older_movies", {})
    year_threshold = older_config.get("year_threshold", 6)

    current_year = datetime.now(timezone.utc).year
    older_cutoff = current_year - year_threshold

    result = []
    for movie in movies:
        if _passes_filter(movie, defaults, genre_overrides, older_config, older_cutoff):
            result.append(movie)

    return result


def _passes_filter(
    movie: dict,
    defaults: dict,
    genre_overrides: dict,
    older_config: dict,
    older_cutoff: int,
) -> bool:
    """Check if a single movie passes the rating filter."""
    imdb = movie.get("imdb_rating")
    rt_expert = movie.get("rt_expert_rating")
    rt_audience = movie.get("rt_audience_rating")

    # No ratings at all → pass (not yet enriched)
    if imdb is None and rt_expert is None and rt_audience is None:
        return True

    # Determine which thresholds to use
    movie_year = movie.get("year", 0)
    is_older = movie_year < older_cutoff

    if is_older:
        # Stricter thresholds for older movies
        thresholds = {
            "min_imdb": older_config.get("min_imdb", defaults.get("min_imdb", 6.0)),
            "min_rt_expert": older_config.get("min_rt_expert", defaults.get("min_rt_expert", 60)),
            "min_rt_audience": older_config.get("min_rt_audience", defaults.get("min_rt_audience", 50)),
        }
    else:
        # Check for genre-specific overrides
        genres = movie.get("genres", [])
        if isinstance(genres, str):
            try:
                genres = json.loads(genres)
            except (json.JSONDecodeError, TypeError):
                genres = []

        thresholds = dict(defaults)
        for genre in genres:
            genre_key = genre.lower().replace(" ", "_")
            if genre_key in genre_overrides:
                # Use genre-specific thresholds (they override defaults)
                genre_thresh = genre_overrides[genre_key]
                for key, val in genre_thresh.items():
                    thresholds[key] = val
                break  # Use first matching genre override

    # Apply thresholds (only check ratings that exist)
    if imdb is not None:
        if imdb < thresholds.get("min_imdb", 0):
            return False

    if rt_expert is not None:
        if rt_expert < thresholds.get("min_rt_expert", 0):
            return False

    if rt_audience is not None:
        if rt_audience < thresholds.get("min_rt_audience", 0):
            return False

    return True


def group_by_year(movies: list[dict], config: dict) -> list[dict]:
    """Group movies into year sections.

    Creates sections for current year down to (current_year - 5),
    plus an "Older" section for everything else.

    Args:
        movies: Filtered list of movie dicts.
        config: Application config dict.

    Returns:
        List of section dicts: {"year": int|None, "label": str, "movies": [...]}
    """
    current_year = datetime.now(timezone.utc).year
    year_range = range(current_year, current_year - 6, -1)

    # Bucket movies by year
    buckets: dict[int | None, list[dict]] = {y: [] for y in year_range}
    buckets[None] = []  # "Older" bucket

    for movie in movies:
        movie_year = movie.get("year", 0)
        if movie_year in buckets:
            buckets[movie_year].append(movie)
        else:
            buckets[None].append(movie)

    # Build sections (only include non-empty ones)
    sections = []
    for year in year_range:
        if buckets[year]:
            sorted_movies = sort_by_genre_priority(buckets[year], config)
            sections.append({
                "year": year,
                "label": str(year),
                "movies": sorted_movies,
            })

    if buckets[None]:
        older_cutoff = current_year - 5
        sorted_movies = sort_by_genre_priority(buckets[None], config)
        sections.append({
            "year": None,
            "label": f"Older (pre-{older_cutoff})",
            "movies": sorted_movies,
        })

    return sections


def sort_by_genre_priority(movies: list[dict], config: dict) -> list[dict]:
    """Sort movies within a section by genre priority from config.

    Movies with a genre higher in the priority list appear first.
    Movies with no matching genre appear at the end.

    Args:
        movies: List of movie dicts.
        config: Application config dict.

    Returns:
        Sorted list of movies.
    """
    priority_list = config.get("genre_priority", [])
    priority_map = {genre.lower(): i for i, genre in enumerate(priority_list)}
    max_priority = len(priority_list)

    def sort_key(movie: dict) -> int:
        genres = movie.get("genres", [])
        if isinstance(genres, str):
            try:
                genres = json.loads(genres)
            except (json.JSONDecodeError, TypeError):
                genres = []

        # Use the best (lowest index) genre priority
        best = max_priority
        for genre in genres:
            genre_key = genre.lower().replace(" ", "_")
            if genre_key in priority_map:
                best = min(best, priority_map[genre_key])

        return best

    return sorted(movies, key=sort_key)
