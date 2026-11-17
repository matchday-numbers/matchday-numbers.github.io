"""Player season totals (from ESPN lineups) and likely suspensions."""
from __future__ import annotations

from collections import defaultdict


def pos_group(abbr):
    """ESPN position code -> G / D / M / F (None for 'SUB' or unknown)."""
    a = (abbr or "").upper()
    if not a or a == "SUB":
        return None
    if a == "G" or a.startswith("GK"):
        return "G"
    if a.startswith(("CD", "CB", "LB", "RB", "SW", "D", "LWB", "RWB")):
        return "D"
    if a.startswith(("F", "CF", "ST", "LW", "RW")):
        return "F"
    if "M" in a:
        return "M"
    return None


def season_players(matches, summaries, team_key_of_side):
    """{team: {player_name: totals}} over the given matches (one competition)."""
    out = defaultdict(dict)
    for m in matches:
        s = summaries.get(m.get("espn_id"))
        if not s:
            continue
        for side in ("home", "away"):
            team = team_key_of_side(m, side)
            for p in (s.get("lineups", {}).get(side) or {}).get("players", []):
                t = out[team].setdefault(p["name"], {"name": p["name"], "id": p.get("id"), "pos": None,
                                                      "apps": 0, "starts": 0, "minutes": 0, "goals": 0,
                                                      "assists": 0, "yellow": 0, "red": 0, "log": []})
                if p["minutes"] > 0:
                    t["apps"] += 1
                t["starts"] += int(p["starter"])
                t["minutes"] += p["minutes"]
                t["goals"] += p["goals"]
                t["assists"] += p["assists"]
                t["yellow"] += p["yellow"]
                t["red"] += p["red"]
                t["pos"] = pos_group(p.get("pos")) or t["pos"]
                t["log"].append((m["date"], p["yellow"], p["red"]))
    return out


def team_games(matches, team):
    return sorted(m["date"] for m in matches if team in (m["home"], m["away"]))


def next_fixtures(events, now):
    """{team espn_id: espn_id of that team's next match in this competition} from a competition's events.
    A ban worked out from cards is served in the team's next match of the same competition, so it is
    counted only there (not in every upcoming fixture)."""
    nxt = {}
    for e in events:
        if e.get("completed") or e.get("status") not in (None, "pre"):
            continue
        ko = e.get("kickoff") or ""
        if ko < now:
            continue
        for side in ("home", "away"):
            tid = (e.get(side) or {}).get("espn_id")
            if tid and (tid not in nxt or ko < nxt[tid][0]):
                nxt[tid] = (ko, e["espn_id"])
    return {t: v[1] for t, v in nxt.items()}


def likely_suspended(league, team, players, matches):
    """Players probably banned for the team's NEXT league match, from cards only.
    Red card in the last league match -> 1 match. Yellow accumulation:
    La Liga every 5th yellow; Premier League 5th yellow within 19 games, 10th within 32."""
    games = team_games(matches, team)
    if not games:
        return []
    last = games[-1]
    out = []
    for p in players.values():
        log = sorted(p["log"])
        if not log or log[-1][0] != last:
            continue
        _, y_last, r_last = log[-1]
        if r_last:
            out.append({"name": p["name"], "position": p.get("pos"), "reason": "sent off last match"})
            continue
        if not y_last:
            continue
        total = sum(x[1] for x in log)
        before = total - y_last
        n = len(games)
        if league in ("champions-league", "europa-league", "conference-league"):
            hit = (before < 3 <= total) or (total >= 5 and total % 2 == 1 and before < total)  # UEFA: 3rd, then 5th, 7th...
        elif league == "premier-league":
            hit = (before < 5 <= total and n <= 19) or (before < 10 <= total and n <= 32)
        else:  # La Liga's rule (every 5th yellow); other leagues' rules differ in detail, so this is approximate
            hit = total // 5 > before // 5
        if hit:
            out.append({"name": p["name"], "position": p.get("pos"),
                        "reason": f"yellow-card ban ({total} yellows)"})
    return out
