# Problem Statement — Series Feed

## 1) Summary (TL;DR)
- **Problem:** The app tracks movie releases from the YTS RSS feed but has no way to ingest, deduplicate, or browse TV series releases, which require parsing season/episode identifiers in addition to grouping quality variants.
- **Impact:** Personal — lack of a consolidated, filtered view of new series episode releases in the same UI as movies.
- **Proposed outcome:** A series ingestion pipeline and web UI tab that fetches the EZTV RSS feed (https://eztv.re/ezrss.xml), parses S##E## identifiers from titles, groups quality variants under the same episode, and presents episodes grouped by season and series name.

## 2) Background / Context
- Current state: The app ingests movies from YTS and displays them in a filtered, grouped UI. TV series have no equivalent pipeline.
- Why now: Natural extension of the existing feed-tracking pattern; EZTV provides a public RSS feed in a parseable format.
- Stakeholders:
  - Business owner: Self (personal project)
  - Technical owner: Self
  - Users: Self

## 3) Scope
### In Scope
- RSS ingestion from https://eztv.re/ezrss.xml on the existing cron schedule
- Regex-based parsing of series title, season number, episode number, and quality from RSS entry titles
- Deduplication by `title + season + episode`, merging quality variants rather than creating duplicate rows
- New `Series` database table and shared-layer model following the existing Movie pattern
- A Series tab in the web UI mirroring the Movies tab layout, with episodes nested under seasons and seasons under series titles
- Read-tracking per series entry
- Email alerting if the EZTV feed is down for > 24 hours (reusing existing alerter logic)

### Out of Scope
- Rating enrichment for series (OMDb lacks reliable episode-level data)
- AI-assisted filtering for series
- Episode descriptions or summaries beyond what the RSS provides
- Downloading or streaming content

## 4) Success Criteria (Measurable)
- [ ] Series episodes from the EZTV RSS feed are ingested into the database on the existing cron schedule
- [ ] Multiple quality variants of the same episode are grouped into a single row (no duplicates)
- [ ] Web UI Series tab displays entries grouped by series title → season → episode
- [ ] Read-tracking works per series entry
- [ ] Email alert fires if the EZTV feed is unreachable for > 24 hours

## 5) Constraints (Known)
- Compliance: N/A (personal project)
- Security: N/A
- Availability: EZTV feed may go down — must detect and alert
- Budget / timeline: N/A
- Tech constraints:
  - Python; MySQL primary, SQLite fallback; same stack as movies
  - Must reuse existing `init_db`, session factory, and alerter patterns
  - EZTV RSS format differs from YTS — title parsing regex needs investigation

## 6) Risks & Unknowns
- Risk: EZTV title format may be inconsistent across entries (e.g., `Show.Name.S01E05.720p` vs. `Show.Name.Season.1.Complete`)
- Risk: Some releases may lack S##E## identifiers and need a fallback grouping strategy
- Unknown: Exact EZTV RSS XML structure — needs inspection before implementing the parser
- Assumption: EZTV feed provides enough metadata (title, magnet/torrent URL) for deduplication

## 7) Decision Needed
- Approve / reject / revise scope
