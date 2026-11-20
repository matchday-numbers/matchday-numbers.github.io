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
  `LINES` in `over`) and ONE highlighted line, the take (owner, 17 Nov 2026): an over or under line with ≥80% chance
  (`model/core.py` TAKE_P, `take_line`: per side the tightest line ≥80% from the full distribution, shown lines first,
  else beyond the bars → extra highlighted row in line order; `model/usual.py` `pick_take`, mirrored by app.js `takeLine`:
  shown first, then the side where the match beats a usual game by more, ties → over). Each line also shows a tick +
  "usual NN%" from `site/data/usual.json` (run.py writes it every run, last season + this one, all 11 comps) and the
  take's text says how often games in the comp do the same. Older estimates without `take_line`: same rule on shown lines.
  Briefs carry the same call as `site_call`. Then
  plus "Numbers alone X, judgement ±Y%". "Why" = reasoning, base, adjustments, subjective view (+ size, numbers alone).
  Track record scores the numbers; the take is scored separately (`result_take`, `accuracy.json` "take").
- Backtest `python -m backtest.recipe` (tune 2024-25, test 2025-26; `RECIPE_TEST_ONLY=1` re-tests). Results in
  `backtest/results_recipe.json` (re-tested 15 Nov 2026 on the 11 comps, 3,357 matches). All beat the plain average on
  1X2 and goals (Segunda only ~1.6%); corners ≈ average. Rule: a comp stays in PREDICTED only if it beats the average on 1X2 and goals.
- Old model (`model/predict.py`, `views.py`, `europe.py` predictor) kept only for estimates frozen before 6 Nov 2026.

## Subjective view (KEY) — `data/overrides/analyst.json`
ONLY for posted matches kicking off within 4 days / 96 h (owner, 18 Nov 2026; was 48 h) (`model/judgement.py` JUDGE_HOURS; run.py attaches a view only then;
`analyst_merge.py` prunes views of matches further out or kicked off 3+ days ago or with no estimate on file).
Per stat: {lean higher/lower/same, adjust_pct (−25..25, sign must match lean), call, text} + overall, sources, written_at.
No double counting (17 Nov 2026): briefs carry `already_counted` (every adjustment the numbers made: missing players,
referee, momentum, h2h, derby, stakes); the view sizes only what is NOT on it (rules in `tools/analyst_rules.md`).
Without a view a stat's verdict line is labelled "The numbers:", with one "Our take:".
It moves the numbers ("our take", above). Written when a match enters the window, then refreshed on a tiered rule (owner,
20 Nov 2026; briefs `--tiers 24:6,48:12,96:24`, 45 min slack): every 24 h at 48–96 h before kick-off, every 12 h at 24–48 h,
every 6 h in the last 24 h (was: once at 48 h + match day at 16 h); unsized old views are redone first. Tools: `tools/analyst_rules.md` (rules),
`tools/analyst_briefs.py OUTDIR --max 80 --batch 20` (who needs a view), `tools/analyst_merge.py FILES` (validate, merge,
prune; `--coverage` report; `--prune` prune only).
Quality rules (owner, 18 Nov 2026, after views went short and ~80% "same, 0"): every stat's text and the 3–5 sentence
`overall` must EXPLAIN the circumstances even at size 0 (who's out, referee, form, stakes, and what the numbers already
count) — never just "already counted, no change"; research ≥3 pages from ≥2 outlets per match incl. one preview/team-news
page for that match. Sizes stay small by design (no double counting; owner declined loosening it, "option C").
Sources show as links on match pages ("Read before writing"), so never tipping/betting pages (buli-tipphilfe.de was
removed from 5 views on 18 Nov). To force a full rewrite now: fire the analyst task with extra text telling it to run
briefs with `--redo-hours 0 --batch 10` (one-off; don't edit the saved prompt for that).

## Self-improvement loop (owner, 17 Nov 2026) — skill `.claude/skills/matchday-self-review/SKILL.md`
- Weekly: `tools/review_mistakes.py` scores the misses (bias, error vs averages, 80% take hit rate, adjustments and
  each adjustment kind, view leans, take vs numbers) into `data/learning/review_last.{md,json}` (+ `history/`), with
  SIGNAL/WATCH/NOISE and `held` (SIGNAL now and WATCH/SIGNAL at a review 5+ days older). Only held findings are
  lessons; at most ONE change per review, through the backtest gate; owner decisions are only proposed.
- `data/learning/lessons.md` (the analyst view task applies its "For the subjective view" section),
  `changelog.md` (changes on trial / kept / reverted), `review_report.md` (weekly report for the owner).
- Model 2 vs model 3 (owner, 17 Nov 2026): model 2 = settings frozen 17 Nov (`data/learning/champion/model2.json`,
  never edit); the pipeline computes it in the shadow for every estimate (`shadow` key; "same" while settings are
  equal; `engine.shadow_recipe`), and `tools/compare_models.py` scores both live → `data/learning/model_compare.md`.
  If model 2 wins, the review reverts its changes. Loop changes must be settings in tuned_recipe.json for this to work.
- **`data/learning/owner_profile.md`: read it at the start of every session. In interactive sessions, add the
  owner's new preferences and decisions (date + their words); scheduled runs only read it.**

## Scheduled tasks (claude.ai, Europe/Madrid)
- "Matchday Numbers analyst view" (trig_0186ymbqezmJYibpT97Rr3P6): 9:07, 13:07, 17:07, 21:07 daily; writes/refreshes
  views (4-day / 96 h window, with sizes) with subagents. It was paused once from the app (12 Nov) — check it's enabled if coverage drops.
- "Matchday Numbers upkeep" (trig_011wZXp3AA8i8evwSxf7ccge): Tue & Fri 8:38; health check, writes
  `data/state/upkeep_last.md`. Early runs quit in <1 min; it works since 12 Nov.
- The WEEKLY REVIEW runs as step 10 of "Matchday Numbers upkeep": the Tuesday 8:38 run (or any run once
  review_last.json is 6+ days old). It always sends the owner a push notification starting "📊 Matchday Numbers ·
  Weekly review (scheduled)" (owner's choice, 17 Nov 2026). Separate weekly tasks created from a session (Monday,
  17 Nov) got no repo when run (fresh session, "no-git-repo") and were deleted: a task that needs the repo must be
  created in the claude.ai routines UI with the repo attached, or live inside the upkeep task.
- Scheduled runs see the repo under its old name and use mcp__github__ tools (owner lucasfrancofedez08-cmd, repo football-stats).

## Other workflows / tools
tests.yml (pytest + headless-browser smoke test of every page), tool.yml (run any `tools/*.py` on GitHub's servers:
inputs script, args), collect-europe.yml, pages-tool.yml (Pages status/cancel/build).

## Known open items
- (Fixed 17 Nov 2026) Suspensions worked out from cards now count only for the team's next match in that competition
  (`players.next_fixtures`, used in run.py). Leagues other than PL/La Liga/UEFA still use La Liga's "every 5th yellow"
  rule as an approximation.
- Retro "model checks" exist for finished matches without frozen estimates (`data/retro/`).
