# Changelog

## v3.8 — 2026-06-03
### Added
- WHOOP DataSource (OAuth 2.0, refresh-token flow) — recovery, sleep, cycle
- Google Health DataSource (post-Fitbit Web API, OAuth 2.0) — sleep, HR, HRV
- `OAuth2DataSource` base class with token caching + 401 cache invalidation
- Setup guides for both integrations under `docs/`
- 45 new tests (OAuth refresh, payload mapping, error matrix) — 312 passing total

## v3.7 — 2026-06-02
### Added
- Biomarker catalog expanded to **118 markers** across 9 categories (CBC, urinalysis, liver/kidney, hormones, lipids, vitamins, metabolic, thyroid, inflammation)
- YAML-driven catalog (`config/biomarker_catalog.yaml`) — add a marker without code changes
- Sparse-rendering policy — only markers with data for a given user appear in their view
- Oura Ring DataSource (Personal Access Token) — sleep, HRV, resting HR, respiratory rate
- `DataSource` ABC + canonical wearables schema for plug-in integrations

## v3.6 — 2026-06-01
### Added
- Page-view + feature interaction tracking (anonymized, opt-in)
- Structured 3-question feedback widget (sentiment + two free-text prompts)
- 7-day NPS micro-survey with re-survey at 30 and 60 days
- Drop-off detector with 7/14/30-day nudges
- Owner analytics dashboard (engagement, funnel, feedback pulse, drop-off watchlist)
- Privacy consent now includes an anonymized-analytics opt-in (default on, revocable)

## v3.5 — 2026-05-31
### Added
- Self-serve account deletion with a 90-day soft-delete recovery window
- Per-user automated data sync (Strava + Apple Health), opt-in per source
- In-app changelog with a "What's new" badge and Home banner
- Lightweight error monitoring with a daily error digest for the owner

### Changed
- Shared logs now scrub PII on account deletion instead of dropping audit rows
