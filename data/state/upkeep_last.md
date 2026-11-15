# Upkeep report — 2026-11-15 17:02 UTC

## Checked
- GitHub Actions: last 6 "update" runs (#119–#124, latest started 15:57 UTC) all succeeded; latest run's update and publish (deploy-pages) jobs both succeeded. Last 5 "tests" runs succeeded (latest 9 Nov; no code pushes since).
- data/state/last_run.json (started 15:58, finished 15:58 UTC, ~1 h ago): errors = none; model 15,688 matches / 546 teams / 10,079 referees linked; 477 estimates made or updated, 111 frozen, 109 scored; team_news_linked 113.
- All 13 competitions have events and predictions (PL 50, La Liga 42, Serie A 40, Bundesliga 36, Ligue 1 36, Eredivisie 35, Primeira 27, Süper Lig 36, Segunda 47, MLS 20, UCL/UEL/UECL 36 each). MLS fotmob_new_stats 0 (playoffs; no new regular-season stats due).
- Cross-check: 0 "single" in every league except Segunda (7, up from 2 eight runs ago — this weekend's Segunda games played during the international break, not yet on football-data.co.uk; normal lag). Conflicts unchanged from earlier today (64 total, mostly yellow-card count differences) — no jump.
- site/data/meta.json updated_at 2026-11-15T15:58 UTC (matches the last run).
- Local test suite: 16 passed (includes headless-browser page check).
- Live site: web fetch of home.json was refused this run (robots_disallowed), so made_at couldn't be read directly. Instead: deploy-pages succeeded at 15:58 UTC and the pages-tool status run reports Pages build_type "workflow", status "built", public.

## Found / fixed
- Nothing broken; no changes to code or settings.
