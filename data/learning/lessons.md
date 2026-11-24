# Lessons

Kept by the matchday-self-review skill (.claude/skills/matchday-self-review/SKILL.md). Every lesson carries its
evidence: finding kind/key, n, z and the review date. Newest first in each section.

## For the subjective view (the analyst view task reads this before writing views)
- (none yet)

## Held lessons, no change possible yet
- 2026-11-24: [take80] corners: 80% takes came true 74% of 91 (given 83%), z = −2.23, HELD (WATCH on 17 Nov).
  Misses on both sides (under 39/51, over 32/40 in calls.json), so the spread looks too narrow live, not a bias.
  The only non-owner fix (refit `nb_alpha`) was tested on 17 Nov and rejected: on 2025-26 (3,357 matches) the
  current spread is already right, and a rerun on the same seasons gives the same values. No change; retest the
  refit once this season's matches can be added to the backtest. No owner proposal: the backtest includes the
  owner's 2x and is calibrated, so there is no evidence the 2x causes it.
- 2026-11-24: [adjust_kind] missing on goals: the number got closer by 0.02 per match (n = 126, z = 2.12), HELD.
  Working as intended; no change needed.

## Watching (not acted on yet)
- 2026-11-24: [adjust] cards: adjustments hurt by 0.09 per match vs base (n = 119, z = −2.07), first-time SIGNAL;
  inside it momentum on cards (n = 107, z = −2.09) and referee on cards (n = 106, z = −2.02), also first-time.
  If it holds next week, the route is a "tuning" setting (form_k / referee_k for cards) through the gate; the
  owner's 2x amplifies these, so propose only if no tuning fix passes.
- 2026-11-24: [adjust_kind] h2h on goals helped by 0.03 per match (n = 92, z = 2.25), first-time SIGNAL.
- 2026-11-24: [take80] cards: 77% of 92 (given 84%), z = −1.72, down from SIGNAL to WATCH.
- 2026-11-24: [views] shots: lean right 23 of 60 (38%), z = −1.81. WATCH; for the view lessons it needs to hold.
- 2026-11-24: [bias] serie-a cards −1.40 (n = 16), la-liga goals −0.60 (n = 20, WATCH twice), premier-league shots on target +1.44 (n = 20).
- 2026-11-17: [take80] cards: 80% takes came true 65% of 31 times (given 84%), z = −3.0. First-time SIGNAL; act
  if it holds at the next review. Possible cause to test then: count spreads (`nb_alpha`) were fitted before
  the owner's 2x amplification.
- 2026-11-17: [take80] corners: 70% of 23 (given 83%), z = −1.63. Same direction as cards.
- 2026-11-17: [adjust_kind] momentum on goals helped by 0.04 per match (n = 44, z = 2.22). Tiny effect.
- 2026-11-17: [bias] la-liga goals −1.08 (n = 10), premier-league corners −1.55 (n = 10), conference-league goals −0.60 (n = 18).

## Applied (see changelog.md)
- (none yet)

## Rejected (tested, did not help)
- 2026-11-17: refit the count spread (`nb_alpha`) with the owner's 2x on, fitted on 2024-25, judged on 2025-26
  (3,357 matches). Cards: 80% takes came true 84.1% (given 83.7%) now vs 84.2% refit; log loss 2.1858 now vs
  2.1862 refit (worse). Corners, shots, shots on target: same picture. The spread is already right on a full
  season, so the live cards miss (65% of 31) is not a spread problem; keep watching it (small sample, or
  something this season the backtest lacks: team news, subjective views).
