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
11 competitions (`pipeline/sources.py`: LEAGUES, DOMESTIC, EUROPE, PREDICTED, FOTMOB_STATS, JOINT_SKIP):
Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Segunda División,
Champions/Europa/Conference League. **Süper Lig and MLS were removed on 15 Nov 2026 at the owner's request** (code, data,
site; don't re-add). Turkish clubs in Europe now count their league games as results only (`model/europe.py` COVERED_SLUGS).
Sources:
- football-data.co.uk CSVs: results + shots/SOT/corners/cards (all leagues).
- ESPN public JSON: fixtures, box-score stats, lineups, scorers, European games, club schedules.
- FotMob public JSON: team news (4 days out), referees. (`pipeline/fotmob_stats.py` = generic FotMob stats source for a
  league marked "stats": "fotmob"; unused now.)
Each league match is cross-checked stat by stat (fd vs ESPN); disagreeing stats are shown with both values and
excluded from the model. State per season in `data/state/<YYZZ>/` (season Jul–Jun, current "2627"); history CSVs in
`data/history/` (5 seasons; referees `referees_*.json`). Placeholder knockout teams ("TBD Home/Away") are skipped.

## Model (owner's recipe) — `model/recipe.py` via `pipeline/engine.py`
- Shown as **45% base + 55% adjusted** (owner asked base −15 pts, adjustments +15 pts in influence).
- Base: `model/ratings.py` penalised time-weighted Poisson ratings per stat (half-life 300 d, 3-year window), home team's
  home vs away team's away, opponent-adjusted vs league average; per-league fits; one joint fit (excl. Segunda) for
  European games. Per-stat team spread `tau_by_stat`.
- Adjustments (each shown with its size): momentum (last 6 games) + head-to-head (20% of it), missing players (share of
  goals+½ assists), referee (cards; record blended with 30 avg games), congestion, derby (+~18% cards), stakes/playoff.
  Sizes measured on 2024-25; `model/tuned_recipe.json` "owner": {"adj_strength": 2.05} amplifies them ~2x — keep it.
- Probabilities: Dixon-Coles goals, negative binomial for counts.
- **Our take** (owner, 15 Nov 2026) — `model/judgement.py`, applied in `engine.make`: each stat's numbers × (1 + view's
  `adjust_pct`/100) (max ±25%; old views with a lean but no size get ±5%), probabilities recomputed; stored as
  `prediction.take` beside the unchanged `prediction.stats`. The site shows the take everywhere (Expected numbers, lines,
  strip, fixture cards via `site_data.pred_summary`); each stat shows 5 bars centred on its expected total (`core.show_lines`, `over_show`; scoring keeps the fixed
  `LINES` in `over`) and ONE highlighted line (17 Nov 2026, `model/usual.py`, mirrored by `standout` in app.js): the shown
  line where the match differs most from a usual game in that competition (`site/data/usual.json`, written by run.py
  every run from last season + this one, all 11 comps); the call must be >50% and ≥6 pts from usual, else "about a
  usual <comp> game"; an under call shows the under side; no usual rates → old rule (tightest line ≥60%). Each line
  shows a tick + "usual NN%". Briefs carry the same call as `site_call`. Then
  plus "Numbers alone X, judgement ±Y%". "Why" = reasoning, base, adjustments, subjective view (+ size, numbers alone).
  Track record scores the numbers; the take is scored separately (`result_take`, `accuracy.json` "take").
- Backtest `python -m backtest.recipe` (tune 2024-25, test 2025-26; `RECIPE_TEST_ONLY=1` re-tests). Results in
  `backtest/results_recipe.json` (re-tested 15 Nov 2026 on the 11 comps, 3,357 matches). All beat the plain average on
  1X2 and goals (Segunda only ~1.6%); corners ≈ average. Rule: a comp stays in PREDICTED only if it beats the average on 1X2 and goals.
- Old model (`model/predict.py`, `views.py`, `europe.py` predictor) kept only for estimates frozen before 6 Nov 2026.

## Subjective view (KEY) — `data/overrides/analyst.json`
ONLY for posted matches kicking off within 48 h (`model/judgement.py` JUDGE_HOURS; run.py attaches a view only then;
`analyst_merge.py` prunes views of matches further out or kicked off 3+ days ago or with no estimate on file).
Per stat: {lean higher/lower/same, adjust_pct (−25..25, sign must match lean), call, text} + overall, sources, written_at.
No double counting (17 Nov 2026): briefs carry `already_counted` (every adjustment the numbers made: missing players,
referee, momentum, h2h, derby, stakes); the view sizes only what is NOT on it (rules in `tools/analyst_rules.md`).
Without a view a stat's verdict line is labelled "The numbers:", with one "Our take:".
It moves the numbers ("our take", above). Written when a match enters the window, redone on match day (kick-off ≤24 h and
view ≥16 h old); unsized old views are redone first. Tools: `tools/analyst_rules.md` (rules),
`tools/analyst_briefs.py OUTDIR --max 80 --batch 20` (who needs a view), `tools/analyst_merge.py FILES` (validate, merge,
prune; `--coverage` report; `--prune` prune only).

## Scheduled tasks (claude.ai, Europe/Madrid)
- "Matchday Numbers analyst view" (trig_0186ymbqezmJYibpT97Rr3P6): 9:07, 13:07, 17:07, 21:07 daily; writes/refreshes
  views (48 h window, with sizes) with subagents. It was paused once from the app (12 Nov) — check it's enabled if coverage drops.
- "Matchday Numbers upkeep" (trig_011wZXp3AA8i8evwSxf7ccge): Tue & Fri 8:38; health check, writes
  `data/state/upkeep_last.md`. Early runs quit in <1 min; it works since 12 Nov.
- Scheduled runs see the repo under its old name and use mcp__github__ tools (owner lucasfrancofedez08-cmd, repo football-stats).

## Other workflows / tools
tests.yml (pytest + headless-browser smoke test of every page), tool.yml (run any `tools/*.py` on GitHub's servers:
inputs script, args), collect-europe.yml, pages-tool.yml (Pages status/cancel/build).

## Known open items
- (Fixed 17 Nov 2026) Suspensions worked out from cards now count only for the team's next match in that competition
  (`players.next_fixtures`, used in run.py). Leagues other than PL/La Liga/UEFA still use La Liga's "every 5th yellow"
  rule as an approximation.
- Retro "model checks" exist for finished matches without frozen estimates (`data/retro/`).
