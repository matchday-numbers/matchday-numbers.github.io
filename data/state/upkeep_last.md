# Upkeep report — 2026-11-17 07:40 UTC (08:40 Madrid)

**Checked**
- `update` workflow: last 6 runs all succeeded (latest 04:15 UTC, both `update` and `publish` jobs green). `tests`: last 4 runs green (latest 16 Nov 19:00 UTC).
- `last_run.json` (finished 04:16 UTC): no errors; model 13,446 matches / 546 teams / 7,619 referees linked; 436 estimates made/updated, 114 frozen, 113 scored; team news linked 117.
- All 11 competitions have events and predictions (PL 50, La Liga 42, Serie A 40, Bundesliga 36, Ligue 1 36, Eredivisie 35, Primeira 27, Segunda 44, UCL 36, UEL 36, UECL 54). Cross-check: 0 "single" everywhere; conflicts 2–10 per league, almost all yellow-card counts (normal level).
- site/data/meta.json `updated_at` 04:15 UTC (within 6 h). Live-site fetch of home.json could not be done this run (fetch permission not granted); the publish job deployed successfully at 04:16 UTC.
- Subjective view coverage: 0 of 0 — international break, no posted match kicks off within 48 h (next: 20 Nov 19:30 UTC). Expected; nothing to spot-check for "our take".

**Found / fixed**
- Nothing broken; no changes made.
