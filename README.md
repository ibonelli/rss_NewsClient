# rss_NewsClient

The fetch CLI is designed to work with cron. For example running it every 15 min via cron means that it fetches feeds every 15 min. Deduplicating in the DB (already-seen items are skipped by url+feed_name uniqueness check).

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
*/15 * * * * cd /home/ignacio/bin/rss_NewsClient && run_pipeline.sh
```

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

## Claude AI filtering

After exporting from the UI you get json files which you can use with Claude command line using the following CLI command:

```bash
run_ai_filtering.sh
```

## Clean Up DB to restart

```sql
DROP DATABASE pelis_feed;
CREATE DATABASE pelis_feed CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
