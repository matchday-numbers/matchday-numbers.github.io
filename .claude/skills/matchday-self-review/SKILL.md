---
name: matchday-self-review
description: Use when running the weekly Matchday Numbers review, when scored estimates or takes missed, when a mistake review (tools/review_mistakes.py) shows SIGNAL or WATCH findings, before changing model settings, take rules or subjective-view rules because of past results, or when the owner states a preference or makes a decision about the site.
---

# Matchday self-review

## Overview
The site learns from its own misses, one proven change at a time, and remembers what the owner wants.
**Core principle: a lesson is a pattern that holds, and a change is kept only if it measurably helps.**
With ~90 checks per review, a few SIGNALs are chance; hand-picked numbers and batches of fixes make it
impossible to know what helped. "No change this week" is a good outcome when nothing held.

Runs weekly as step 10 of the "Matchday Numbers upkeep" scheduled task (Tuesdays), or when the owner asks.

## Files (data/learning/)
| File | What it is | Who writes it |
|---|---|---|
| review_last.md / .json, history/ | this week's findings (`tools/review_mistakes.py`) | the script |
| lessons.md | lessons with evidence: for the subjective view, watching, applied, rejected | this skill |
| changelog.md | every change made from a lesson, its test result and its check date | this skill |
| owner_profile.md | the owner's preferences and decisions, from their own words | interactive sessions only |
| review_report.md | this week's plain-language report for the owner | this skill |

## Weekly review (the steps, in order)
1. `python tools/review_mistakes.py`, then read review_last.md, lessons.md, changelog.md, owner_profile.md.
2. **Check last changes first.** For each changelog entry "on trial", look at its target finding now: better →
   mark it "kept"; worse or unchanged after 2 reviews → revert it (same gate, step 5) and mark "reverted".
3. **Sort this week's findings:**
   - `held: true` (SIGNAL now, WATCH/SIGNAL last time, same sign) → a lesson. Add it to lessons.md.
   - SIGNAL for the first time, or WATCH → lessons.md "Watching" with its numbers. No change.
   - NOISE → nothing.
4. **Pick at most ONE lesson to act on** (the one with the largest |z|), and its route. When the cause could be
   an owner decision AND a setting the owner did not decide (e.g. cards takes overconfident: the owner's 2x
   amplification, or the count spread `nb_alpha` fitted before it), try the non-owner fix through the gate first;
   propose an owner change only if no non-owner fix passes.

| Lesson about | Route | Gate |
|---|---|---|
| numbers: bias, error, take80 calibration, an adjustment kind hurting | a setting in `model/tuned_recipe.json` "tuning"/"rating", or model code | backtest (step 5) |
| subjective view: leans on a stat wrong, or the take worse than the numbers | a line in lessons.md "For the subjective view" (the analyst task reads it) | the held finding itself, n ≥ 30 |
| anything the owner decided (owner_profile.md "Decisions", `tuned_recipe.json` "owner", the 80% take rule, the 45/55 split, the competitions) | **no change**: write a proposal with the evidence in review_report.md and send a push notification | owner says yes |

5. **Backtest gate** (numbers route). Make the change, then `RECIPE_TEST_ONLY=1 python -m backtest.recipe`
   (or a full re-tune, `RECIPE_BASE_GRID='[[300,0.04]]' python -m backtest.recipe`, ~15 min, when the fix is a
   setting the tuner fits). Compare `backtest/results_recipe.json` with the committed version (`git diff`):
   keep only if the target metric improves AND win/draw/loss and goals do not get worse in any competition.
   Otherwise `git checkout` the files and record "rejected" in lessons.md. Every value you commit came out of a
   run; never type in a value no run produced. Run `python -m pytest -q` before pushing.
6. **Record** in changelog.md: date; the finding (kind/key, n, z); the change (file, old → new); the backtest
   numbers before/after; status "on trial"; the check: "target finding at the next 2 reviews".
7. **Report**: write review_report.md for the owner: what was checked, what held, what changed and why, what is
   being watched, any proposal waiting for them. Plain words, the honest hit rates. Commit everything
   (data/learning, any changed files) and push (CLAUDE.md commit rules). Push notification only for a proposal.

## Owner profile
Write to owner_profile.md only from the owner's own words or choices in a conversation: date, what they said or
chose, where. A scheduled run has no owner in it, so it reads the profile and never adds to it. Never infer a
preference from silence, from a task prompt, or from what would be convenient. A newer decision replaces an older
one: mark the old line "(replaced <date>)". At the end of any interactive session where the owner decided or
asked for something, add it.

## Red flags: stop and go back to the steps
| Thought | Reality |
|---|---|
| "Use X as a stopgap until the refit runs" | A value no run produced is a guess. Run the gate or change nothing. |
| "SIGNAL with z = −3, act now" | First-time SIGNALs are often chance among ~90 checks. Watch it; act when it holds. |
| "Several clear fixes, do them all" | One change per review, or you cannot tell what helped. Queue the rest in lessons.md. |
| "The owner wants visible change every week" | Only owner_profile.md says what they want. An honest "nothing held" is a result. |
| "The bias is huge on 10 matches" | n < 30 is never a lesson, however large. |
| "The owner's setting is clearly what hurts" | Owner decisions are theirs: propose with evidence, do not change. |
| "Add a CI guard / CLAUDE.md rule too" | Not a learning step. Record the lesson in lessons.md; the handoff points there. |

## Common mistakes
- Comparing backtest results to memory instead of `git diff backtest/results_recipe.json`.
- Forgetting step 2, so a change that did not help stays forever.
- Writing a lesson without its numbers (kind/key, n, z, date). Every lesson needs them to be checked later.
