# Changelog

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
