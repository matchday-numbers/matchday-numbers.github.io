# Owner profile (Lucas)

What the owner wants, learned from their own words and decisions. Every session and scheduled task that changes the
site reads this first. Add to it whenever the owner states a preference, decides something or reacts to a change
(date + what they said or chose + where). Never infer a preference from silence. Newest decisions win; when one
replaces an older line, mark the old line "(replaced <date>)" instead of deleting it.

## How to work with them
- Do the work yourself; ask only when it is truly important. Be honest and direct; short, plain answers.
  When they ask a question, answer it plainly first (said repeatedly, CLAUDE.md).
- They like explanations "with details and easy to get": what's wrong, a real example from the site, the fix,
  the cost (17 Nov 2026, critique session).
- They want to see things before they ship when the look changes: asked for a picture of fix 5(b) before approving
  it (17 Nov 2026).
- When asked "any questions, I'm here": ask only the one question that changes the result; they answered quickly
  (17 Nov 2026, 80% take).
- They want scheduled tasks kept in step with every change ("remember to adapt each schedule task", 17 Nov 2026).

## What the site must be
- For regular fans; information, not advice. Keep the disclaimer banner; never "lock", "sure thing", "guaranteed",
  "recommend"; no betting links or sites (CLAUDE.md).
- Keep the current design unless they ask (CLAUDE.md).
- Publish the track record including misses (CLAUDE.md).

## Decisions on the model (do not undo without asking)
- 45% base + 55% adjustments; adjustments amplified about 2x (owner adj_strength 2.05) (15 Nov 2026).
- Subjective view is KEY; written only within 48 h (window replaced 18 Nov 2026, see below); it moves the numbers into "our take", max ±25% (15 Nov 2026).
- Süper Lig and MLS removed; never re-add (15 Nov 2026).
- The highlighted take is an over or under line with an 80%+ chance; when none of the 5 bars reaches 80%, go
  further out and add an extra row (they chose "go further out", 17 Nov 2026).
- They accepted the critique's honesty fixes without pushback: card bans only for the next match, no double
  counting in views, "The numbers" label without a view (17 Nov 2026).

- Asked for an ongoing self-improvement loop: find mistakes, learn from them, improve the prediction procedures,
  and get to know them better over time (17 Nov 2026). Built as the matchday-self-review skill, run weekly.

- Wants the weekly review's one-line summary on their phone every week, also when nothing changed, clearly marked
  as the scheduled task ("send me the summary every week. how can i identify that it is an scheduled task",
  17 Nov 2026).
- Wants model 2 vs model 3 compared on real matches before believing the self-review helps ("as it is potential
  = uncertain yet, make sure you compare model 2 and 3", 17 Nov 2026).

- Said no to both open questions ("Don't add any of the open questions", 18 Nov 2026):
  - No "how often our 80% takes came true" on the track record page.
  - Keep the 2x amplification for cards and shots too (owner adj_strength 2.05 for every stat). Don't propose
    dropping it again unless a weekly review has new, held evidence against it.
- Subjective view window: 4 days (96 h) before kick-off instead of 48 h ("instead of developing a subjective view
  48 hours before a match, I want you to make it 4 days before any match starts. Change the scheduled task and
  everything related to it", 18 Nov 2026). Views refresh when 48 h old and are redone on match day. (refresh rule replaced 20 Nov 2026, see below)
- Subjective views must explain the circumstances, not just say "already counted, no change", and must rest on
  real research (at least 3 pages from 2+ outlets per match). Said after views got short and mostly "same"
  ("why does the subjective view has such less of an impact now? why it does not explain any circustances as it
  used to?" then "do A and B", 18 Nov 2026). Double-counting rule unchanged; loosening sizes (option C) not chosen.

- Views refreshed more often to catch news (20 Nov 2026: "updated the views of the matches more oftenly to find news
  or anything that may determine a stat"; chose option A + extra runs, "go with option 1, apply it on weekends only and
  the other time for weekdays"): refresh every 24 h at 48–96 h before kick-off, every 12 h at 24–48 h, every 6 h in
  the last 24 h. Analyst runs: daily 9:07, 13:07, 17:07, 19:07, 21:07; weekends also 11:07 and 14:07 (Madrid).
  (They first chose 19:37 and 14:37; moved to :07 because a second task couldn't push — "go with option 2", 20 Nov 2026.)

## Open questions they have not answered yet
- Whether to run the analyst task's research subagents on Sonnet 5.5 instead of Opus to save usage: they chose to
  wait 2-3 days of real usage under the new schedule first ("wait 2-3 to find out how much it does consume and then
  decide", 20 Nov 2026). A usage report is scheduled for Mon 23 Nov 10:00 Madrid.
- (answered 18 Nov 2026) Whether to add "how often our 80% takes came true" to the track record page (offered 17 Nov 2026).
- (answered 18 Nov 2026) Whether to drop the 2x amplification for cards and shots (raised 17 Nov 2026).
