# Upkeep run — 2026-11-19 12:55 UTC (Thursday, scheduled)

**Result: all healthy, nothing to fix.**

Checked:
- Workflows: last 6 `update` runs (incl. publish) succeeded, latest 10:25 UTC; last 5 `tests` runs succeeded.
- last_run.json (finished 10:27 UTC): no errors; model 13,437 matches / 546 teams / 7,619 referees linked;
  459 estimates made or updated, 113 scored; team news linked 177. meta.json updated_at 10:25 UTC.
- All 11 competitions have events and predictions (PL 55, La Liga 42, Serie A 45, Bundesliga 42, Ligue 1 36,
  Eredivisie 39, Primeira 27, Segunda 47, UCL 36, UEL 36, UECL 54). Cross-check: 0 single, conflicts 2–10 per
  league (yellow-card counts, as usual).
- usual.json: all 11 comps, 207–613 games each (content unchanged since 17 Nov, so not in today's commit).
- Take lines: 400 estimates made this morning, 2,275 stat blocks (numbers + take) — every one has a take_line side
  at 80%+; every file has `shadow` ("same").
- Subjective view: 64 of 64 posted matches within 96 h have a sized view. Spot-check Twente–Willem II: take
  adjust_pct matches the view (goals −3, SOT −2); sizes rest on a suspension the numbers don't see, no double counting.
- Card bans: 4 upcoming Champions League bans checked; each is the team's next match in that competition.
- Live site: web fetch refused by the site's robots rules, so not fetched directly; the latest publish job succeeded.

Fixed: nothing needed.
Weekly review: not due (last review 17 Nov, 2 days ago).
