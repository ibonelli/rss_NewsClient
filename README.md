# rss_NewsClient

## TLDR

The fetch CLI is designed to work with cron. For example running it every 15 min via cron means that it fetches feeds every 15 min. Deduplicating in the DB (already-seen items are skipped by url+feed_name uniqueness check).

```bash
.venv/bin/python3 src/cli/main.py
.venv/bin/python3 src/webui/main.py
```

The web UI is a long-running service and has no auto-reload, any changes to routes.py/app.js will require a manual restart to take effect.

## First install & setup (using MySQL)

```bash
apt install mariadb-server -y
sudo apt install python3-sqlalchemy python3-feedparser python3-yaml python3-httpx python3-venv -y
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run `mariadb` as root:

```sql
CREATE DATABASE pelis_feed CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON pelis_feed.* TO 'pelis_feed_user'@'localhost' IDENTIFIED BY '<password>';
FLUSH PRIVILEGES;
EXIT;
```

Finally if we run the CLI it will create the tables:

```bash
source .venv/bin/activate
# fetching
python3 src/cli/main.py
```

To run the filtering:

```bash
source .venv/bin/activate
# filtering
python3 src/cli/filter.py
```

## Cron setup

There is a script that runs both (fetch and filter):

```bash
run_pipeline.sh
```

To run it every 15 mins you use:

```
MAILTO="ignacio@nachodigital.com.ar"
*/15 * * * * cd /home/ignacio/bin/rss_NewsClient && ./run_pipeline.sh
```

`run_pipeline.sh` writes everything to `logs/pelis_feed_pipeline.log` and prints **nothing** on a clean run, so cron sends no email. If a run exits non-zero or logs an `ERROR` / `CRITICAL` / `Traceback` line, it prints a report (the error lines plus that run's log section), and cron mails it to `MAILTO`.

- Don't redirect the script's output in the crontab line (`>> file 2>&1`), and don't call `src/cli/*.py` directly: either one bypasses the report (or mails every INFO/WARNING line).
- Always set `MAILTO` to a full address. Without it, cron mails the bare local user, and Postfix appends `$myorigin` (by default the hostname, e.g. `mail.nachodigital.com.ar`). To fix that for all local mail: `sudo postconf -e 'myorigin = $mydomain' && sudo systemctl reload postfix`.
- Feed fetch failures are logged at `ERROR`, so a feed that's down triggers an email on every run until it recovers.

## Running the UI

```bash
source .venv/bin/activate
# To keep it running
nohup .venv/bin/python3 src/webui/main.py >> logs/webui.log 2>&1 &
echo $! > logs/webui.pid
```

## Checking UI health

Check the health endpoint to confirm the DB has data: `http://127.0.0.1:8080/api/health`

Check the movies API directly: `http://127.0.0.1:8080/api/movies`

If total_count is 0 there but the ingester logged insertions, the filtering rules are probably too strict (all movies have no ratings yet — they should pass through, but worth verifying).

## APIs

```
http://127.0.0.1:8080/api/health
http://127.0.0.1:8080/api/movies
http://127.0.0.1:8080/api/series
```

## UI page routes

Each feed type has its own bookmarkable URL (client-side routed, backed by
FastAPI routes that serve the same SPA shell):

```
http://127.0.0.1:8080/movies
http://127.0.0.1:8080/series
http://127.0.0.1:8080/news
http://127.0.0.1:8080/news/<feed name>
http://127.0.0.1:8080/design
http://127.0.0.1:8080/design/<feed name>
```

`<feed name>` matches a `name` entry under `news_feeds` / `design_feeds` in
`config.yaml` (URL-encoded, e.g. spaces as `%20`).

## Claude AI filtering

After exporting from the UI you get json files which you can use with Claude command line using the following CLI command:

```bash
run_ai_filtering.sh
```

## Backing up the DB

`tools/backup_db.sh` reads `database.url` from `config.yaml` and writes a timestamped, gzipped backup to `./backups/` (git-ignored) or to the directory given as first argument. MySQL uses `mysqldump --single-transaction`; SQLite uses `sqlite3 .backup`. Both are safe while the web UI is running.

```bash
tools/backup_db.sh                      # -> backups/pelis_feed-YYYYMMDD-HHMMSS.sql.gz
BACKUP_KEEP_DAYS=14 tools/backup_db.sh  # also delete backups older than 14 days
```

Daily cron example (silent on success; on failure prints one line, which cron mails to `MAILTO`):

```
30 3 * * * cd /home/ignacio/bin/rss_NewsClient && { BACKUP_KEEP_DAYS=14 tools/backup_db.sh >> logs/backup.log 2>&1 || echo "DB backup failed, see logs/backup.log"; }
```

Restore (MySQL): `gunzip -c backups/FILE.sql.gz | mysql -u USER -p pelis_feed`

## Clean Up DB to restart

```sql
DROP DATABASE pelis_feed;
CREATE DATABASE pelis_feed CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
