# Subjective view: how to write it

The subjective view is human-style judgement on top of the statistical numbers. It is written ONLY for
matches the site posts that kick off within the next 4 days (96 hours) (`model/judgement.py` JUDGE_HOURS); matches
further away get no view. For each stat it gives a lean and a size (`adjust_pct`), and the site moves the
numbers by that size to show **our take**: the expected number, the likely range and every line percentage
are worked out again from the moved number. So the size matters: it changes what the site shows.

It is shown at the top of the match page, and in each stat's "Our take" line and "Why" box (next to the
reasoning, the base, the adjustments and the numbers alone). The numbers alone are kept and scored in the
track record; our take is scored separately against them.

## Views follow the news

A view is written when a match enters the 4-day window and then refreshed more often as kick-off nears (owner,
20 Nov 2026): every 24 h while the match is 48-96 h away, every 12 h at 24-48 h, and every 6 h in the last 24 h and every 3 h in the last 6 h
(match day: the latest team news, expected lineups and the referee). Runs (25 Nov 2026): weekdays 9:07 and 17:07,
Saturday-Sunday also 14:07 (Madrid). When a brief carries
`current_view`, start from it but re-research: keep what still holds, change the lean, size or call where
the news changed (a key player back or injured, a manager sacked, rotation announced), and say what changed.
A brief with `current_view_needs_sizes: true` is an older view without sizes: redo it with sizes.

## Input

A brief per match (from `tools/analyst_briefs.py`): competition, kick-off, teams, table positions and form,
win/draw/loss probabilities, and for each stat the numbers' expected total (home/away split, before any
judgement) and `site_call`: the take line the site highlights for the numbers alone (the over or under line with
at least an 80% chance, the tightest one; your size moves it, since the take is recomputed from the moved numbers), plus missing players, referee,
derby/stakes flags, `already_counted` (every adjustment the numbers already made, with its effect: do not size
these again), hours left to kick-off and `max_adjust_pct` (25).

## Lessons from past views

Before writing, read `data/learning/lessons.md`, section "For the subjective view": lessons the weekly review
proved from scored matches (e.g. a stat where leans have been wrong too often). Apply them; a lesson there
overrides your instinct. Do not read the other sections as rules: "Watching" is not proven yet.

## Research (web search and web fetch; never from memory)

Look for what the numbers can't see, published recently (the last few days; team news from the last 48 hours):
- injuries and suspensions (including anyone missing from the brief's list), expected or confirmed lineups
- rotation before or after a European or cup game, fixture congestion, travel
- manager situation (new, under pressure, sacked), dressing-room or club turmoil
- motivation: title race, European places, relegation, promotion play-offs, already qualified or eliminated
- tactics and style (sits deep, presses high, set-piece threat, wide play that drives corners)
- the referee's style and recent card counts, when known (the numbers already count his record: only move for
  something they can't see); weather when it matters

Good sources: ESPN, Sky Sports, BBC Sport, The Athletic, the clubs' and competitions' own sites, AS, Marca,
Relevo, Mundo Deportivo, Kicker, L'Equipe, Gazzetta dello Sport, Record, A Bola, Fanatik, Hurriyet,
MLSsoccer.com, SoccerNews, Statz.ai. Judge a source by the site as a whole: never use a site whose main purpose is betting (bookmakers, odds
pages, tipster or tipping-game sites such as buli-tipphilfe.de, pages with bookmaker links or offers). A news or
preview page that is mostly team news and line-ups is fine even if it ends with a predicted score or a pick
(e.g. Sports Mole, starting11): use its news, ignore its pick, never repeat the pick in the view.
The sources are shown as links on the site.
Cross-check anything important (an injury, a ban, a sacking) with a second source; if only one source had
it, say so ("one report says ..."). Do not invent facts. If you find nothing for a match, say the view rests
on form and context and lean "same" where nothing points either way.

Research every match properly (owner, 18 Nov 2026): read **at least 3 pages per match, from at least 2
different outlets**, and at least one of them a preview or team-news page for THIS match (not only a
league-wide roundup). Roundups are a good start, not the whole job. Look at both teams. If, after a real
search, fewer than 3 useful pages exist (small leagues), list what you read and say in `overall` that news
was thin. Take the time this needs; depth matters more than speed.

## Who does what: Sonnet researches, Opus writes (owner, 26 Nov 2026)

This section overrides the scheduled task's step 3 on how subagents are used (it is there to cut usage). The research
and the writing are split:

1. **Research = Sonnet subagents.** Split each batch file into groups of at most 5 matches and give each group to a
   subagent started with the Agent tool's `model: "sonnet"` (run them in parallel). Each one reads this file's
   "Research" section and the briefs of its matches, does the research (web search/fetch, at least 3 pages from 2+
   outlets per match, one a preview/team-news page for that match, both teams, cross-check), and writes FACTS ONLY to
   `/tmp/research/<batch>_<group>.md`: per match the injuries/bans/lineups found (and how they differ from the brief's
   missing players and `already_counted`), rotation, manager, motivation, tactics, referee, weather, what changed since
   `current_view` if any, and every source as title + URL + outlet + date. No leans, no sizes, no views. It replies with
   one line: the file path and the matches done.
2. **View = Opus.** When a batch's research files exist, give the batch to ONE subagent started with `model: "opus"`
   (batches in parallel). It reads this whole file, the "For the subjective view" section of
   `data/learning/lessons.md`, the batch's briefs and the research notes, and writes the views (leans, `adjust_pct`,
   calls, texts, `overall`, sources from the notes) to `/tmp/views/out_<batch>.json`, checked with
   `python tools/analyst_merge.py --check <file>`. It may do a quick extra search only to settle a gap or a conflict
   in the notes. All judgement (no double counting, sizes, wording) is the Opus writer's job.
3. Then step 4 (merge) as usual. If a Sonnet researcher fails or returns empty notes for a match, the Opus writer
   researches that match itself rather than skipping it.

## Output (exact format)

```json
{"matches": {
  "<espn match id>": {
    "overall": "Two or three sentences with the main context of the match.",
    "goals": {"lean": "lower", "adjust_pct": -8, "call": "Around 2.2 goals", "text": "The numbers say 2.4 goals. I lean lower: ..."},
    "corners": {"lean": "same", "adjust_pct": 0, "call": "Around 10 corners", "text": "..."},
    "cards": {"lean": "higher", "adjust_pct": 10, "call": "Over 4.5 cards", "text": "..."},
    "shots": {"lean": "...", "adjust_pct": 0, "call": "...", "text": "..."},
    "shots_on_target": {"lean": "...", "adjust_pct": 0, "call": "...", "text": "..."},
    "sources": ["https://...", "https://..."],
    "written_at": "2026-11-09T18:30:00Z"
  }
}}
```

- `lean`: compared with the numbers' expected total. Take a side when the research supports one; "same" only when
  nothing points either way.
- `adjust_pct`: how far you would move the numbers' expected total, in percent: a whole number from -25 to 25.
  It must agree with the lean (higher > 0, lower < 0, same = 0). Size it to the evidence: 3-6 for a mild lean
  (one doubtful player, a hunch from style), 7-12 for a clear reason (a key striker out that the numbers don't
  know about, heavy rotation, a manager just sacked), 13-25 only for something big and confirmed (several
  first-choice players out that the numbers don't know about, a dead-rubber with a reserve side).
  **Never count anything twice.** The brief's `already_counted` lists what the numbers have already moved for
  (the players in `missing`, the referee, momentum, head-to-head, derby, stakes), each with its effect. Size only
  what is NOT on that list: a player missing who isn't in `missing`, a confirmed lineup that differs, rotation,
  a manager change, motivation, weather, tactics. A player in `missing` or the referee can only justify a size if
  the news differs from what the numbers assumed (e.g. the banned player's appeal won, the absence is longer or
  the referee was changed); then say so. If nothing new turns up, lean "same" with 0.
  Your own number is the numbers' expected total x
  (1 + adjust_pct / 100); write it in `call` or `text` so it matches (e.g. 28.2 shots and -12 -> about 24.8).
- `call`: your judgement call in a few words (a line or a rough number). No percentages or probabilities.
- `text`: two or three plain sentences. Start from the numbers' expected total, then give the reasons for your
  lean and its size, naming the players, manager, referee or situation involved. **Explain the circumstances
  even when the size is 0** (owner, 18 Nov 2026): say what is going on that matters for this stat (who is out
  and what that means for it, the referee and his card record, form, style, motivation) and which of it the
  numbers already count, e.g. "Without Budimir, Osasuna's main scorer, they rarely score at home; the numbers
  already take his absence off, about -0.2 goals, so I stay at 2.8". Never just "already counted, no change" or
  "I found no news the numbers can't see".
- `overall`: three to five sentences with the main context of the match: league positions and what is at stake,
  form, key absences and returns on both sides (and whether the numbers count them), the managers' situation,
  rotation or congestion, the referee if named. A reader should understand the match from it alone.
- `sources`: the pages you actually read for this match (at least one).
- English, plain words, no hype. Never write "lock", "sure thing" or "guaranteed", never tell anyone to bet.

Validate with `python tools/analyst_merge.py --check <file>` before merging.
