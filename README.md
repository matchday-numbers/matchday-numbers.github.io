# Matchday Numbers

Past match statistics and statistical estimates for upcoming matches in ten leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Süper Lig, Segunda División, MLS), and the Champions, Europa and Conference League. An information tool, not betting advice: every estimate shows its inputs, its uncertainty and its track record.

**Website:** https://matchday-numbers.github.io/

## How it runs

A GitHub Actions workflow (`.github/workflows/update.yml`) runs every 3 hours:

1. Downloads results and match stats from **football-data.co.uk** (for MLS, which it covers with results only, from **FotMob**: `pipeline/fotmob_stats.py`), fixtures, team stats, lineups, goals and European matches from **ESPN's public feed**, and team news and referees from **FotMob**.
2. Cross-checks the two sources stat by stat (football-data.co.uk or FotMob against ESPN). A stat the sources disagree on is shown with both values and left out of the model for that match.
3. Makes predictions for every match in the next 31 days, all thirteen competitions. A prediction is rewritten on each run until kick-off, then **frozen** (never touched again) and scored after the match. The git history of `data/predictions/` is the proof that each one existed before kick-off.
4. Writes the site data (`site/data/`) and publishes `site/` to GitHub Pages.

Team news (injured and suspended players) comes from **FotMob's public feed** for matches in the next 4 days. When FotMob has nothing, suspensions are worked out from cards. `data/overrides/injuries.json` is a manual override that is merged on top.

## Model

One recipe for every match, league or European (`model/recipe.py`, run by `pipeline/engine.py`):

**final = 45% base + 55% adjusted** (the owner's choice; the first version was 60/40)

- **Base (45%)** — `model/ratings.py`: a penalised, time-weighted Poisson rating fit per stat (half-life 300 days, last three seasons). The home team's home attack against the away team's away defence (and the reverse), opponent-adjusted and measured against the competition's average; small team-specific home/away deviations. League games use a fit on that league only; European games use one joint fit over every league, every club's domestic and qualifying games (ESPN team schedules) and the European matches, so clubs share a scale. How far a team may sit from its league's level (`tau_by_stat`) was tuned per stat: wide for goals, narrow for corners and shots, where raw team averages overstate real differences.
- **Adjustments (55%)**, each listed on the match page with its effect on the final number: momentum (last 6 games in any competition vs what the ratings expected, with head-to-head as 20% of it), missing players (factor 1 − the player's share of team goals + ½ assists; a missing regular keeper or defender adds 3% to the opponent), referee for cards (his record blended with 30 average games), fixture congestion, derby and high stakes. Sizes are measured at 40% weight; then, at the owner's request (`owner.adj_strength` in `model/tuned_recipe.json`, 2.05), their combined effect is amplified about 2x on a log scale. That cut the base's share of what moves an estimate from about 76% to 61% on matches near kick-off. The 45/55 display is defined so the two parts add up exactly to the final number.
- **Probabilities**: Dixon-Coles for goals, negative binomial for corners, cards and shots.
- **Reasoning**: each stat gets plain-language reasoning (where the base sits against the average and why, what the adjustments did, the bottom line), shown in its "Why" box.
- **Subjective view**: written judgement per match and stat (`data/overrides/analyst.json`: lean higher/lower/same, a judgement call and the reasons), written by a scheduled task from recent news. It's shown in each stat's "Why" box and next to "Our call", and never mixed into the numbers.

`backtest/recipe.py` tunes on 2024-25 and tests once on 2025-26 (4,130 matches, all thirteen competitions, walk-forward by week), against plain averages and against the previous method. Results in `backtest/results_recipe.json`, settings in `model/tuned_recipe.json`. On the test season:

- Win/draw/loss and goals beat the plain average in every competition (Brier 0.595 vs 0.648 overall) and are level with the previous method where it existed (within about 1%; best gain Premier League +1.1%). The edge is large in the top European leagues and the Süper Lig (win/draw/loss 5% to 17% better than the average) and small in the Segunda División (1.6%) and MLS (3.3%); all three new leagues also beat the average on win/draw/loss and goals in 2024-25.
- Cards beat the average in 10 of 13 competitions, shots in 9, shots on target in 10 (by small margins); corners are level with the average (−2% to +2%).
- With adjustments at about 2x their measured size (the owner's choice), the test error changed by: goals and win/draw/loss ±0.0%, corners −0.1%, shots on target −0.3%, shots −0.8%, cards −1.1% (slightly less accurate). Goals and win/draw/loss still beat the average in every competition.
- Momentum measured as weak: recent form adds little once the base weights recent games, so its tuned size is small. Derbies: +18% cards. Stakes and congestion: no measurable effect (shown for information, size 0).

Referees for every competition come from FotMob (`tools/collect_referees.py` for history, live for upcoming matches; for MLS they come with FotMob's match stats). MLS history is collected with `tools/collect_fotmob_stats.py`. MLS played calendar years until 2026 and moves to a July-May season from 2027-28: its 2026-27 window starts in February 2026, so the site has the whole 2026 season and the short spring 2027 season, and its table shows the latest regular season only (both conferences together, as for the Supporters' Shield). Finished matches without a frozen estimate get a "model check" (`data/retro/`), clearly labelled and outside the track record. Older modules (`model/predict.py`, `model/views.py`, `model/europe.py` predictor) are kept for earlier frozen estimates and the previous backtests.

## Layout

```
model/       prediction model (no network)
pipeline/    sources, merge & cross-check, players, predictions, site data
backtest/    tuning and test on past seasons
data/        history CSVs, state, frozen predictions, overrides
site/        static website (index.html, app.js, styles.css, data/)
tests/       python -m pytest -q
```
