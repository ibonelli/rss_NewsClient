# Runbook — pelis-feed

## SLOs / SLIs
- Personal project, best-effort — no formal SLOs. Availability target is "reachable when Ignacio wants to check it"; no on-call rotation.

## Alerts
(See `docs/02-planning/Observability-Plan.md` for the full list.)

- **A-001 — Feed downtime**
  - Meaning: A feed (movie or news) has been unreachable for >24 hours (FR-007).
  - Immediate action: Email arrives via local SMTP (`alerting` config in `config.yaml`). Check the feed URL manually in a browser; if the upstream feed changed URL or format, update `config.yaml` (`feed.url`, `series_feed.url`, or the relevant `news_feeds`/`design_feeds` entry).
  - Escalation: None — single-owner project.
- **A-002 — Enrichment degradation**
  - Meaning: >50% of OMDb enrichment attempts failed in a single ingester run (log warning only, no email).
  - Immediate action: Check `enrichment.api_key` in `config.yaml` hasn't expired/hit rate limits; check OMDb API status.
- **A-003 — Import failure**
  - Meaning: An AI-filtered news import payload failed schema validation or DB persistence (log warning only).
  - Immediate action: Check the Filter Processor logs (`journalctl -u pelis-feed-filter` or cron mail) for the validation error.

## Deployment — Apache reverse proxy on a subdomain, password-protected

Deploys the web UI behind Apache on its own subdomain with HTTP Basic Auth and Let's Encrypt TLS. Target stack: Debian/Ubuntu + Apache2. Placeholders to replace: `news.nachodigital.com.ar` (subdomain), `SERVER_IP` (server's public IP), `/opt/pelis-feed` (install path).

### 1. DNS
Add an A record (and AAAA if the server has IPv6) at your DNS provider:
```
pelis   A    SERVER_IP        TTL 300
```
Wait for propagation (`dig news.nachodigital.com.ar`) before continuing — the Let's Encrypt HTTP challenge in step 7 needs it resolvable.

### 2. Deploy the app
```bash
sudo useradd --system --home /opt/pelis-feed --shell /usr/sbin/nologin pelisfeed
sudo git clone <your-repo-url> /opt/pelis-feed
cd /opt/pelis-feed
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt
sudo cp config.yaml.example config.yaml
sudo -e config.yaml   # set database.url, enrichment.api_key, feed URLs, and confirm:
```
Keep the app bound to localhost only — Apache is the only thing that should ever reach port 8080:
```yaml
webapp:
  host: "127.0.0.1"
  port: 8080
```
```bash
sudo chown -R pelisfeed:pelisfeed /opt/pelis-feed
```

### 3. systemd service for the web UI
`/etc/systemd/system/pelis-feed-web.service`:
```ini
[Unit]
Description=rssfeed web UI
After=network.target

[Service]
Type=simple
User=<linux-user-to-run>
Group=<linux-group-to-run>
WorkingDirectory=/home/www/rss_NewsClient
ExecStart=/home/www/rss_NewsClient/venv/bin/python /home/www/rss_NewsClient/src/webui/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pelis-feed-web
sudo systemctl status pelis-feed-web
curl -s http://127.0.0.1:8080/api/health   # sanity check, from the server itself
```

Cron for the batch processes stays as-is (two chained CLI processes per ADR-006 — Ingester then Filter Processor):
```
0 */2 * * * cd /opt/pelis-feed && ./venv/bin/python src/cli/main.py && ./venv/bin/python src/cli/filter.py
```

### 4. Enable required Apache modules
```bash
sudo a2enmod proxy proxy_http headers ssl rewrite
sudo systemctl restart apache2
```

### 5. Create the password file (Basic Auth)
```bash
sudo apt install apache2-utils   # provides htpasswd, if not already present
sudo htpasswd -c /etc/apache2/.htpasswd-pelis <youruser>
# -c only on first user; drop -c and rerun to add more users later
```

### 6. HTTP vhost (port 80) — needed first so certbot's ACME challenge can pass
`/etc/apache2/sites-available/news-nachodigital.conf`:
```apache
<VirtualHost *:80>
    ServerName news.nachodigital.com.ar

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8080/
    ProxyPassReverse / http://127.0.0.1:8080/

    <Location />
        AuthType Basic
        AuthName "pelis-feed"
        AuthUserFile /etc/apache2/.htpasswd-pelis
        Require valid-user
    </Location>

    ErrorLog ${APACHE_LOG_DIR}/pelis-error.log
    CustomLog ${APACHE_LOG_DIR}/pelis-access.log combined
</VirtualHost>
```

```bash
sudo a2ensite news-nachodigital.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```
Verify `http://news.nachodigital.com.ar` prompts for Basic Auth and proxies to the app before moving to TLS.

### 7. TLS via Let's Encrypt
```bash
sudo apt install certbot python3-certbot-apache
sudo certbot --apache -d news.nachodigital.com.ar
```
Certbot adds a `:443` block with the cert and (if accepted) a redirect from `:80` to `:443`, while preserving the `<Location>` Basic Auth block. Confirm the resulting `news-nachodigital-le-ssl.conf` still has the `AuthType Basic` block inside the `:443` vhost.

Certbot's renewal timer is installed automatically:
```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

### 8. Firewall
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```
Do not open 8080 externally — it's only reachable via `127.0.0.1` (already enforced by `webapp.host` in step 2).

### 9. Verify end-to-end
- `curl -I https://news.nachodigital.com.ar` → expect `401` without credentials.
- `curl -I -u youruser:pass https://news.nachodigital.com.ar` → expect `200`.
- Browser: `/movies`, `/series`, `/news` load and client-side routing works (all served by `routes.py:serve_spa_route` returning the same `index.html`; Apache just proxies every path through).
- `/api/movies`, `/api/health` respond under the new origin.
- `sudo journalctl -u pelis-feed-web -f` while testing, to catch backend errors.

Note: `src/webui/app.py` hardcodes CORS `allow_origins` to `http://127.0.0.1:8080`/`http://localhost:8080`. Not an issue here since the browser only ever talks to `https://news.nachodigital.com.ar` (same-origin through the proxy) — only relevant if something needs to call the API cross-origin from a different domain.

## Common tasks

### Restart the web UI
```bash
sudo systemctl restart pelis-feed-web
```

### Add/remove a Basic Auth user
```bash
sudo htpasswd /etc/apache2/.htpasswd-pelis newuser      # add
sudo htpasswd -D /etc/apache2/.htpasswd-pelis olduser   # remove
```

### Rotate the OMDb API key
Edit `enrichment.api_key` in `config.yaml`, then `sudo systemctl restart pelis-feed-web`.

### Recover from feed downtime alert
See A-001 above.

### Recover from Apache config error
```bash
sudo apache2ctl configtest   # find the syntax error before reloading
sudo systemctl reload apache2
```

## Post-incident checklist
- [ ] Root cause documented
- [ ] Preventative action created (config change, alert threshold, monitoring gap, etc.)
