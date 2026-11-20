# Upkeep run — Fri 20 Nov 2026, 07:40 UTC (08:40 Madrid)

**Result: healthy, nothing to fix.**

Checked:
- update workflow: last 6 runs all succeeded, both jobs (latest run 04:16 UTC: update + publish/deploy-pages OK). tests workflow: last run (18 Nov) passed; no failures since.
- last_run.json: no errors (incl. usual rates / model 2 shadow); finished 04:17 UTC (<6 h); model 13,436 matches, 546 teams, 7,619 referees linked; 506 estimates made/updated, 114 frozen, 113 scored; team news linked 181.
- All 11 competitions have events and predictions (PL 59, La Liga 52, Serie A 50, Bundesliga 45, Ligue 1 36, Eredivisie 44, Primeira 36, Segunda 58, UCL 36, UEL 36, UECL 54). Cross-check: 0 "single" anywhere; conflicts 2–10 per league, almost all yellow-card counts (normal level, no jump).
- usual.json: covers all 11 comps, each 207–613 games. Unchanged in git since 17 Nov because no new games finished in the international break (counts match last_run).
- meta.json updated_at 04:16 UTC.
- Take lines: every stat of all 506 upcoming estimates (numbers and take) has a take_line with a side ≥80%; every file has "shadow".
- Subjective view coverage: 68 of 68 posted matches within 96 h have sized views; 4 due a match-day refresh (the analyst task handles that).
- Spot-check Elversberg–Freiburg (21 Nov): take matches the view (all 0%); view explains missing defenders as already counted — no double counting.
- Card bans: Mouriño's yellow-card ban sits on his team's next Champions League match (25 Nov); no earlier unplayed CL fixture — next-fixture rule OK.
- Weekly review: not due (last review 17 Nov, 3 days ago).

Could not check: the live site JSON (home.json / usual.json) — this run's network couldn't reach matchday-numbers.github.io. The deploy job succeeded at 04:18 UTC, so the site should be current.
