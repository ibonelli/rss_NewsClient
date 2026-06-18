# rss_NewsClient

First install & setup (using MySQL):

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
python3 src/cli/main.py
```
