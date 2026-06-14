# Problem Statement — pelis-feed

## 1) Summary (TL;DR)
- **Problem:** No automated way to collect, filter, and report on movie releases from the YTS RSS feed.
- **Impact:** Personal — lack of a consolidated, filtered view of new movie releases with quality ratings data.
- **Proposed outcome:** An automated pipeline that ingests RSS data into SQLite, filters by multiple criteria, and produces an HTML report.

## 2) Background / Context
- Current state: Manual browsing of the YTS RSS feed with no persistent storage or filtering.
- Why now: Desire to automate movie discovery with quality filtering (ratings, genre, year).
- Stakeholders:
  - Business owner: Self (personal project)
  - Technical owner: Self
  - Users: Self

## 3) Scope
### In Scope
- RSS feed ingestion from `https://yts.ag/rss`
- Scheduled polling (every ~2 hours)
- SQLite database for persistent storage
- Filtering logic: year, genre, grouping same-name movies, IMDb rating, Rotten Tomatoes rating
- HTML report generation from filtered data
- Email alerting when RSS feed is down for > 1 day

### Out of Scope
- Downloading or streaming movies
- Multi-user support
- Web UI for browsing (only static HTML report)
- Mobile notifications (email only)

## 4) Success Criteria (Measurable)
- [ ] RSS feed data is ingested into SQLite on a recurring schedule (~2h)
- [ ] HTML report is generated with filtered, grouped movie data
- [ ] Email alert is sent if the feed is unreachable for > 24 hours
- [ ] Duplicate movies (same name) are grouped correctly in the report

## 5) Constraints (Known)
- Compliance: N/A (personal project)
- Security: N/A
- Availability: Feed may go down — must detect and alert
- Budget / timeline: N/A
- Tech constraints:
  - SQLite as the database
  - Two separate processes (scheduler + report generator)

## 6) Risks & Unknowns
- Risk: RSS feed (`yts.ag`) could change format, move URL, or go permanently offline
- Risk: Feed downtime detection requires reliable scheduling infrastructure
- Unknown: Exact filtering thresholds (minimum IMDb rating, minimum RT score) — to be defined in requirements
- Unknown: How Rotten Tomatoes ratings will be sourced (not typically in RSS feeds — may need enrichment)
- Assumption: The RSS feed provides enough metadata (title, year, genre) for basic filtering

## 7) Decision Needed
- Approve / reject / revise scope
- Clarify: How will Rotten Tomatoes ratings be obtained? (API, scraping, manual?)
- Clarify: What are the minimum rating thresholds for inclusion in the report?
