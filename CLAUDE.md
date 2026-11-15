# Matchday Numbers — handoff for a new session

Football stats + statistical estimates site for regular fans, run fully hands-off by Claude.
Owner: Lucas (CUNEF student, Europe/Madrid). Read README.md too (method details, test results).

## Owner's rules (always)
- Do the work yourself; only ask if TRULY important. Be honest and direct; short answers.
- Never scrape websites beyond the public JSON/CSV feeds already used. Ask before any paid service.
- Banner on estimate pages: "Statistical estimates, not advice. Football is unpredictable — use your own judgement."
- Never "lock", "sure thing", "guaranteed"; no betting links/sites. Estimates freeze at kick-off; publish the track record incl. misses.
- Keep the current design unless asked; the subjective view is KEY for the page.
- Commits: `git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit`, message ends with
  `Co-Authored-By: Claude <noreply@anthropic.com>`; no `--amend`; `git pull --rebase -X theirs origin main` before push.

## Where things are
- Repo: matchday-numbers/matchday-numbers.github.io (formerly lucasfrancofedez08-cmd/football-stats; GitHub redirects).
- Site: https://matchday-numbers.github.io/ (GitHub Pages, source "GitHub Actions"; works on phones).
- The sandbox can't reach football sites: all fetching happens in GitHub Actions. git/gh to this repo works.

## Pipeline (`.github/workflows/update.yml`, every 3 h at :17, also on pushes to pipeline/model/site/overrides)
Job `update` runs `python -m pipeline.run`, commits data, packages `site/`; job `publish` deploys (deploy-pages).
13 competitions (`pipeline/sources.py`: LEAGUES, DOMESTIC, EUROPE, PREDICTED, FOTMOB_STATS, JOINT_SKIP):
Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Süper Lig, Segunda División, MLS,
Champions/Europa/Conference League. Sources:
- football-data.co.uk CSVs: results + shots/SOT/corners/cards (all leagues except MLS).
- ESPN public JSON: fixtures, box-score stats, lineups, scorers, European games, club schedules.
- FotMob public JSON: team news (4 days out), referees, and MLS match stats (`pipeline/fotmob_stats.py`).
Each league match is cross-checked stat by stat (fd or FotMob vs ESPN); disagreeing stats are shown with both values and
excluded from the model. State per season in `data/state/<YYZZ>/` (season Jul–Jun, current "2627"); history CSVs in
`data/history/` (5 seasons; MLS from 2022-23 via `tools/collect_fotmob_stats.py`; referees `referees_*.json`).
MLS: calendar-year season until 2026, Jul–May from 2027-28; `run.py season_start()` gives MLS a Feb-2026 window for 2627,
`roll_history()` keeps only Jul–Jun rows, MLS table = latest regular season both conferences (Supporters' Shield).
Placeholder playoff teams ("TBD Home/Away") are skipped.

## Model (owner's recipe) — `model/recipe.py` via `pipeline/engine.py`
- Shown as **45% base + 55% adjusted** (owner asked base −15 pts, adjustments +15 pts in influence).
- Base: `model/ratings.py` penalised time-weighted Poisson ratings per stat (half-life 300 d, 3-year window), home team's
  home vs away team's away, opponent-adjusted vs league average; per-league fits; one joint fit (excl. Segunda, MLS) for
  European games. Per-stat team spread `tau_by_stat`.
- Adjustments (each shown with its size): momentum (last 6 games) + head-to-head (20% of it), missing players (share of
  goals+½ assists), referee (cards; record blended with 30 avg games), congestion, derby (+~18% cards), stakes/playoff.
  Sizes measured on 2024-25; `model/tuned_recipe.json` "owner": {"adj_strength": 2.05} amplifies them ~2x — keep it.
- Probabilities: Dixon-Coles goals, negative binomial for counts. Each stat: "Our call" = tightest line ≥60%;
  "Why" box = reasoning, base, adjustments, subjective view.
- Backtest `python -m backtest.recipe` (tune 2024-25, test 2025-26; `RECIPE_TEST_ONLY=1` re-tests). Results in
  `backtest/results_recipe.json`. All 13 comps beat the plain average on 1X2 and goals (Segunda/MLS only ~2–3%);
  corners ≈ average. Rule: a comp stays in PREDICTED only if it beats the average on 1X2 and goals.
- Old model (`model/predict.py`, `views.py`, `europe.py` predictor) kept only for estimates frozen before 6 Nov 2026.

## Subjective view (KEY) — `data/overrides/analyst.json`
Every posted match (upcoming with an estimate, ~480) gets a researched view per stat: {lean higher/lower/same, call,
text} + overall, sources, written_at. Shown at the top of the match page, next to "Our call" and in each "Why" box.
Never changes the numbers. Views change with the news: redone at least every 5 days, every 2 days in the last week,
and within 36 h of kick-off. Tools: `tools/analyst_rules.md` (rules), `tools/analyst_briefs.py OUTDIR --max N --batch 20`
(who needs a view), `tools/analyst_merge.py FILES` (validate, merge, prune; `--coverage` report).

## Scheduled tasks (claude.ai, Europe/Madrid)
- "Matchday Numbers analyst view" (trig_0186ymbqezmJYibpT97Rr3P6): 9:07, 13:07, 21:07 daily; writes/refreshes views
  with subagents. It was paused once from the app (12 Nov) — check it's enabled if coverage drops.
- "Matchday Numbers upkeep" (trig_011wZXp3AA8i8evwSxf7ccge): Tue & Fri 8:38; health check, writes
  `data/state/upkeep_last.md`. Early runs quit in <1 min; it works since 12 Nov.
- Scheduled runs see the repo under its old name and use mcp__github__ tools (owner lucasfrancofedez08-cmd, repo football-stats).

## Other workflows / tools
tests.yml (pytest + headless-browser smoke test of every page), tool.yml (run any `tools/*.py` on GitHub's servers:
inputs script, args), collect-europe.yml, pages-tool.yml (Pages status/cancel/build).

## Known open items
- Suspensions worked out from cards are applied to every upcoming fixture of a team, not just the next one (the views
  correct for it in words; the numbers don't yet). Fix in run.py / players.likely_suspended: only the next fixture.
- Retro "model checks" exist for finished matches without frozen estimates (`data/retro/`).
