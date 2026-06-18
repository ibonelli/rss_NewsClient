# rss_NewsClient

## First install & setup (using MySQL)

```bash
apt install mariadb-server -y
sudo apt install python3-sqlalchemy python3-feedparser python3-yaml python3-httpx -y
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run `mariadb` as root:

```sql
CREATE DATABASE pelis_feed CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON pelis_feed.* TO 'pelis_feed_user'@'localhost' IDENTIFIED BY 'MeHeit4uaH6I!yai';
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

```bash
run_pipeline.sh
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

