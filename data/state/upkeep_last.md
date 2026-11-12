# Upkeep report — 2026-11-12 19:05 UTC

## Checked
- GitHub Actions: last 6 "update" runs (run #94–#99, latest 16:22 UTC) all succeeded, both jobs (update + publish/deploy-pages). Last 5 "tests" runs succeeded (latest 9 Nov).
- data/state/last_run.json (started 16:22, finished 16:23 UTC, ~2.7 h ago): errors = none; model 15,683 matches / 546 teams / 10,072 referees linked; 449 estimates made or updated, 103 frozen, 102 scored; team_news_linked 112.
- All 13 competitions have events and predictions (PL 47, La Liga 32, Serie A 36, Bundesliga 34, Ligue 1 35, Eredivisie 34, Primeira 24, Süper Lig 35, Segunda 44, MLS 20, UCL/UEL/UECL 36 each).
- Cross-check: 0 "single" matches in every league; 64 conflicts in total (mostly yellow-card count differences), unchanged across the last 8 runs — no jump.
- site/data/meta.json updated_at 2026-11-12T16:22 UTC (matches the last run).
- Local test suite: 16 passed (includes headless-browser page check).
- Live site home.json: made_at 2026-11-12T19:17 UTC (re-checked later in the session) — current.
- International break: no league results since 8–9 Nov, so frozen (103) and scored (102) counts are unchanged, as expected. 4 matches ESPN marks Postponed (Estoril–Maritimo, Castellón–Eibar, Granada–Tenerife, Andorra–Mallorca) are correctly not treated as finished.

## Found / fixed
- Nothing broken; no changes to code or settings.
