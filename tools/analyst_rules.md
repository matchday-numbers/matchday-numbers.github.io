# Subjective view: how to write it

Every match the site posts (every upcoming fixture with an estimate) gets a subjective view: human-style
judgement next to the statistical numbers. It is shown at the top of the match page, next to each stat's
"Our call" and in each stat's "Why" box. It never changes the numbers.

## A view follows the news

A view is a judgement on what is known today, so it changes when the news changes: a view written two weeks
before a match will often differ from the one written the day before. Each match's view is redone:
weekly while the match is far off, and again in the day and a half before kick-off with team news, lineups
and the referee. When you redo a view, the brief includes the current one: keep what still holds, change
what the news has changed, and never copy it without checking.

## Views change with the news

A view is a judgement on the news of the day, not a one-off. Each match's view is rewritten as kick-off
approaches: at least every five days, every two days in the final week, and in the last 36 hours with the
latest team news, lineups and referee. When a brief carries `current_view`, start from it but re-research:
keep what still holds, change the lean or the call when the news has changed (a key player back or injured,
a manager sacked, rotation announced), and say what changed. Two views of the same match written two weeks
apart can and often should differ.

## Input

A brief per match (from `tools/analyst_briefs.py`): competition, kick-off, teams, table positions and form,
win/draw/loss probabilities, and for each stat the site's expected total (home/away split) and "our call"
line, plus missing players, referee, derby/stakes flags and how many days are left to kick-off.

## Research (web search and web fetch; never from memory)

Look for what the numbers can't see, published recently (last 7-10 days; for matches more than a week away,
the latest available):
- injuries and suspensions (including anyone missing from the brief's list), expected or confirmed lineups
- rotation before or after a European or cup game, fixture congestion, travel
- manager situation (new, under pressure, sacked), dressing-room or club turmoil
- motivation: title race, European places, relegation, promotion play-offs, already qualified or eliminated
- tactics and style (sits deep, presses high, set-piece threat, wide play that drives corners)
- the referee's style and recent card counts, when known; weather when it matters

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
    "goals": {"lean": "higher|lower|same", "call": "Under 2.5 goals", "text": "The numbers say 2.4 goals. I lean lower: ..."},
    "corners": {"lean": "...", "call": "Around 10 corners", "text": "..."},
    "cards": {"lean": "...", "call": "Over 4.5 cards", "text": "..."},
    "shots": {"lean": "...", "call": "...", "text": "..."},
    "shots_on_target": {"lean": "...", "call": "...", "text": "..."},
    "sources": ["https://...", "https://..."],
    "written_at": "2026-11-09T18:30:00Z"
  }
}}
```

- `lean`: compared with the site's expected total. Take a side when the research supports one; "same" only when
  nothing points either way.
- `call`: your judgement call in a few words (a line or a rough number). No percentages or probabilities.
- `text`: two or three plain sentences. Start from the site's number, then give the reasons for your lean,
  naming the players, manager, referee or situation involved.
- `overall`: two or three sentences. If kick-off is more than 3 days away, start with "Early view:" and base it
  on the latest form and news; it is refreshed with team news in the day before kick-off.
- `sources`: the pages you actually read for this match (at least one).
- English, plain words, no hype. Never write "lock", "sure thing" or "guaranteed", never tell anyone to bet.

Validate with `python tools/analyst_merge.py --check <file>` before merging.
