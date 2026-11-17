# Lessons

Kept by the matchday-self-review skill (.claude/skills/matchday-self-review/SKILL.md). Every lesson carries its
evidence: finding kind/key, n, z and the review date. Newest first in each section.

## For the subjective view (the analyst view task reads this before writing views)
- (none yet)

## Watching (not acted on yet)
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
