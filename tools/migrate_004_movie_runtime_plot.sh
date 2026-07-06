#!/usr/bin/env bash
# Idempotent migration: add runtime and plot columns to the movies table,
# backfill existing movies.qualities rows from flat-string shape (["1080p"])
# to the new {quality, size} object shape ([{"quality": "1080p", "size": null}]),
# and repair movies.genres rows corrupted by the pre-fix genre-fusion bug
# (last genre token fused with "Size: ... Runtime: ... <plot>").
# Safe to re-run — skips each ALTER/backfill/repair step that's already applied.
set -euo pipefail

DB_URL="${DATABASE_URL:-}"

if [ -z "$DB_URL" ]; then
    # Fall back to reading from config.yaml via python
    DB_URL=$(python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
cfg = load_config()
print(cfg["database"]["url"])
EOF
)
fi

echo "Applying migration 004 (movies.runtime, movies.plot, qualities backfill, genre-fusion repair) to: $DB_URL"

python - <<'EOF'
import json
import re
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from src.cli.fetcher import _SIZE_PATTERN, _RUNTIME_PATTERN
from sqlalchemy import create_engine, text

cfg = load_config()
db_url = cfg["database"]["url"]
engine = create_engine(db_url)

with engine.connect() as conn:
    is_sqlite = db_url.startswith("sqlite")
    if is_sqlite:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(movies)")).fetchall()]
    else:
        cols = [row[0] for row in conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movies'"
        )).fetchall()]

    if "runtime" not in cols:
        stmt = "ALTER TABLE movies ADD COLUMN runtime VARCHAR(50)" if is_sqlite else "ALTER TABLE movies ADD COLUMN runtime VARCHAR(50) NULL"
        conn.execute(text(stmt))
        conn.commit()
        print(f"Added runtime column ({'SQLite' if is_sqlite else 'MySQL'}).")
    else:
        print("runtime column already exists. Nothing to do.")

    if "plot" not in cols:
        stmt = "ALTER TABLE movies ADD COLUMN plot TEXT" if is_sqlite else "ALTER TABLE movies ADD COLUMN plot TEXT NULL"
        conn.execute(text(stmt))
        conn.commit()
        print(f"Added plot column ({'SQLite' if is_sqlite else 'MySQL'}).")
    else:
        print("plot column already exists. Nothing to do.")

    # Backfill: convert legacy flat-string qualities (["1080p"]) to
    # {quality, size} objects ([{"quality": "1080p", "size": null}]).
    # Skips rows already in dict shape — safe to re-run.
    rows = conn.execute(text("SELECT id, qualities FROM movies")).fetchall()
    updated = 0
    for row_id, qualities_json in rows:
        try:
            qualities = json.loads(qualities_json) if qualities_json else []
        except (json.JSONDecodeError, TypeError):
            continue

        if not qualities or all(isinstance(q, dict) for q in qualities):
            continue  # already migrated (or empty) — nothing to do

        new_qualities = [
            q if isinstance(q, dict) else {"quality": q, "size": None}
            for q in qualities
        ]
        conn.execute(
            text("UPDATE movies SET qualities = :qualities WHERE id = :id"),
            {"qualities": json.dumps(new_qualities), "id": row_id},
        )
        updated += 1

    conn.commit()
    print(f"Backfilled qualities shape on {updated} movie row(s) ({len(rows) - updated} already up to date).")

    # Repair genres corrupted by the pre-fix genre-fusion bug: the last genre
    # token got fused with "Size: ... Runtime: ... <plot>" (and the plot's own
    # commas further split it across multiple trailing array elements). The
    # original Size/Runtime/plot text is still fully recoverable from what was
    # stored — rejoin the corrupted tail with ", " and re-derive genre/size/
    # runtime/plot the same way the fixed fetcher.py parser does.
    rows = conn.execute(text("SELECT id, title, genres, runtime, plot FROM movies")).fetchall()
    repaired = 0
    for row_id, title, genres_json, runtime, plot in rows:
        try:
            genres = json.loads(genres_json) if genres_json else []
        except (json.JSONDecodeError, TypeError):
            continue

        bad_idx = next(
            (i for i, g in enumerate(genres) if "Size:" in g or "Runtime:" in g), None
        )
        if bad_idx is None:
            continue  # not corrupted — nothing to do

        clean_genres = genres[:bad_idx]
        corrupted_text = ", ".join(genres[bad_idx:])

        last_genre_match = re.match(r"^(.*?)\s*(?:Size:|Runtime:)", corrupted_text)
        last_genre = last_genre_match.group(1).strip() if last_genre_match else None
        if last_genre:
            clean_genres.append(last_genre)

        size_match = _SIZE_PATTERN.search(corrupted_text)
        runtime_match = _RUNTIME_PATTERN.search(corrupted_text)
        recovered_runtime = runtime_match.group(1).strip() if runtime_match else None

        plot_start = 0
        for match in (runtime_match, size_match):
            if match:
                plot_start = match.end()
                break
        recovered_plot = corrupted_text[plot_start:].strip() or None

        conn.execute(
            text("UPDATE movies SET genres = :genres, runtime = :runtime, plot = :plot WHERE id = :id"),
            {
                "genres": json.dumps(clean_genres or ["Unknown"]),
                "runtime": runtime or recovered_runtime,
                "plot": plot or recovered_plot,
                "id": row_id,
            },
        )
        repaired += 1
        print(f"  Repaired genres for '{title}' (id={row_id}): {clean_genres}")

    conn.commit()
    print(f"Repaired genre-fusion corruption on {repaired} movie row(s) ({len(rows) - repaired} already clean).")
EOF
