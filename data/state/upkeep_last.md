# Upkeep run — 2026-11-24 08:38–08:55 Madrid (Tuesday, weekly review day)

**Checked**
- update workflow: last 4 runs green (latest 04:21 UTC, update + publish). One failure on 23 Nov 20:19 UTC: a push race
  with the analyst commit ("cannot lock ref"), so it was transient. The next runs were fine.
- tests workflow: run 31 failed on 23 Nov (#/calls 404 because calls.json didn't exist until the first data run
  after the "Our calls" commit). Re-run 32 passed. Local `pytest`: 27 passed.
- last_run.json: no errors; finished 04:23 UTC; 13,524 matches, 7,687 referees linked; 439 estimates made or updated,
  182 frozen. All 11 comps have events, 0 "single" checks, normal conflict counts (yellow cards); predictions 27–54 each.
  usual: all 11 comps, 207–624 games. usual.json and calls.json are in the latest data commit (calls.json: 175
  matches, latest finished 23 Nov 20:00 UTC, each with hits/n).
- Live site: web fetch was blocked in this run (permission timeout), so home.json/usual.json weren't fetched live.
  The publish job of the 04:21 UTC run succeeded.
- Take lines and shadow: all 439 upcoming estimates updated in the last 6 h have a take_line ≥ 0.80 for every stat
  (numbers and take), shadow "same" and a top-level `calls`.
- Subjective views: 62 of 62 posted matches within 96 h have a sized view (9 due a match-day refresh). Spot check
  Lyon–Lillestrøm (EL, 26 Nov): take adjust_pct matches the view (goals −2, shots −3, SoT −3). No double counting:
  the view says Openda/Sulc are already counted and sizes only rotation before Monaco.
- Card bans: Hoffenheim–Augsburg (29 Nov) lists Kabak "sent off last match". There's no earlier unplayed Hoffenheim
  Bundesliga fixture, so the next-fixture rule holds.

**Fixed**: nothing needed.

**Weekly review**: Model 2 vs 3 identical. Held: corners 80% takes overconfident (74% of 91); missing players help
goals. No change (the spread refit already failed the gate on 17 Nov). Watching: cards adjustments (form/referee).
