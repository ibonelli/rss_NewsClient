# Problem Statement — pelis-feed

## 1) Summary (TL;DR)
- **Problem:** No automated way to collect, filter, and track movie releases from the YTS RSS feed or to manage and classify news from configurable RSS/Atom feeds.
- **Impact:** Personal — lack of a consolidated, filtered view of new movie releases with quality ratings data, and no way to track and classify news items of interest.
- **Proposed outcome:** A two-process application: a cron-driven ingester that fetches and stores movie and news RSS data, and a web-based UI for browsing, read-tracking, and triggering on-demand enrichment. News feeds support unfiltered, regex-filtered, and AI-assisted classification (via JSON export/import with an external tool).

## 2) Background / Context
- Current state: Manual browsing of the YTS RSS feed with no persistent storage or filtering; no consolidated news tracking.
- Why now: Desire to automate movie discovery with quality filtering (ratings, genre, year) and to track relevant news in one place.
- Stakeholders:
  - Business owner: Self (personal project)
  - Technical owner: Self
  - Users: Self

## 3) Scope
### In Scope
- RSS feed ingestion from `https://yts.ag/rss` (movies) and configurable news RSS/Atom feeds
- Scheduled polling (~every 2 hours via cron)
- MySQL (primary) or SQLite (fallback) database for persistent storage
- Movie filtering by year, genre, IMDb and Rotten Tomatoes ratings; on-demand enrichment from a free external API
- News feed types: unfiltered (store all), filtered (regex matching), AI-assisted (export/import workflow)
- Web-based UI (FastAPI + React) for browsing, read-tracking, and movie enrichment
- JSON export of unprocessed news items for external AI classification; JSON import of AI results back into the application
- Email alerting when any configured feed is down for > 24 hours

### Out of Scope
- Downloading or streaming movies
- Multi-user support
- Mobile notifications (email only)
- Hosting or invoking any AI classification tool — the application only exports/imports JSON

## 4) Success Criteria (Measurable)
- [ ] RSS feed data is ingested into the database on a recurring schedule (~2h)
- [ ] Web UI displays filtered, grouped movie data with read-tracking and on-demand rating enrichment
- [ ] News items from all configured feeds are stored and displayed with read-tracking
- [ ] AI-assisted feeds can export unread items to JSON and import AI-classified results, which appear in the News tab
- [ ] Email alert is sent if any configured feed is unreachable for > 24 hours
- [ ] Duplicate movies (same name or torrent URL) are grouped correctly in the UI

## 5) Constraints (Known)
- Compliance: N/A (personal project)
- Security: N/A
- Availability: Feeds may go down — must detect and alert
- Budget / timeline: N/A
- Tech constraints:
  - Python; MySQL primary, SQLite fallback
  - Two separate processes (cron ingester + FastAPI web app)
  - No paid APIs for movie enrichment
  - No direct AI service integration — external AI processing via JSON export/import only

## 6) Risks & Unknowns
- Risk: RSS feeds could change format, move URL, or go permanently offline
- Risk: Feed downtime detection requires reliable scheduling infrastructure
- Unknown: Long-term availability/reliability of free movie rating APIs (OMDb, etc.)
- Assumption: RSS feeds provide enough metadata (title, year, genre) for basic filtering
- Assumption: The external AI tool is operated separately and consumes/produces the defined JSON format

## 7) Decision Needed
- Approve / reject / revise scope
