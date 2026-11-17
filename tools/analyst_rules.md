# Subjective view: how to write it

The subjective view is human-style judgement on top of the statistical numbers. It is written ONLY for
matches the site posts that kick off within the next 48 hours (`model/judgement.py` JUDGE_HOURS); matches
further away get no view. For each stat it gives a lean and a size (`adjust_pct`), and the site moves the
numbers by that size to show **our take**: the expected number, the likely range and every line percentage
are worked out again from the moved number. So the size matters: it changes what the site shows.

It is shown at the top of the match page, and in each stat's "Our take" line and "Why" box (next to the
reasoning, the base, the adjustments and the numbers alone). The numbers alone are kept and scored in the
track record; our take is scored separately against them.

## Views follow the news

A view is written when a match enters the 48-hour window and redone on match day (kick-off within 24 h, view
older than 16 h) with the latest team news, expected lineups and the referee. When a brief carries
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
MLSsoccer.com, SoccerNews, Statz.ai. Never use betting sites (no bookmakers, odds or tipster pages).
Cross-check anything important (an injury, a ban, a sacking) with a second source; if only one source had
it, say so ("one report says ..."). Do not invent facts. If you find nothing for a match, say the view rests
on form and context and lean "same" where nothing points either way.

Work efficiently: one search usually covers a team's news for several of its matches, and league-wide
injury roundups cover many teams at once.

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
  lean and its size, naming the players, manager, referee or situation involved.
- `overall`: two or three sentences with the main context of the match.
- `sources`: the pages you actually read for this match (at least one).
- English, plain words, no hype. Never write "lock", "sure thing" or "guaranteed", never tell anyone to bet.

Validate with `python tools/analyst_merge.py --check <file>` before merging.
