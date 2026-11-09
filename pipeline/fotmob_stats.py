"""Match stats from FotMob, for leagues football-data.co.uk covers with results only (MLS).

Gives the same records as a football-data.co.uk CSV (results, shots, shots on target, corners, cards,
fouls, referee), so the rest of the pipeline treats FotMob as that league's first source and ESPN as
the second one it is cross-checked against.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from pipeline.sources import FOTMOB, fetch

# FotMob stat key -> (home column, away column) in football-data.co.uk naming
KEYS = {"total_shots": ("HS", "AS"), "ShotsOnTarget": ("HST", "AST"), "corners": ("HC", "AC"),
        "yellow_cards": ("HY", "AY"), "red_cards": ("HR", "AR"), "fouls": ("HF", "AF")}
COLUMNS = ["Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HS", "AS", "HST", "AST",
           "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR", "Referee"]
_SCORE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)")


def league_matches(fotmob_id, season=None):
    """Every match of one FotMob league season: [{fotmob_id, home, away, kickoff, finished, hg, ag}]."""
    q = f"{FOTMOB}/leagues?id={fotmob_id}" + (f"&season={urllib.parse.quote(str(season), safe='')}" if season else "")
    data = fetch(q, "fotmob")
    if not data:
        return None
    out = []
    for m in (json.loads(data).get("fixtures") or {}).get("allMatches") or []:
        st = m.get("status") or {}
        hg = ag = None
        sc = _SCORE.match(st.get("scoreStr") or "")
        done = bool(st.get("finished")) and not st.get("cancelled") and not st.get("awarded")
        if done and sc:
            hg, ag = int(sc.group(1)), int(sc.group(2))
        out.append({"fotmob_id": str(m["id"]), "home": m["home"]["name"], "away": m["away"]["name"],
                    "kickoff": st.get("utcTime"), "finished": done and hg is not None, "hg": hg, "ag": ag})
    return out


def parse_details(d):
    """matchDetails JSON -> {HS, AS, ..., Referee}; a stat FotMob doesn't have stays missing."""
    c = d.get("content") or {}
    per = ((c.get("stats") or {}).get("Periods") or {}).get("All") or {}
    out = {}
    for g in per.get("stats") or []:
        for x in g.get("stats") or []:
            k, v = x.get("key"), x.get("stats")
            if k in KEYS and KEYS[k][0] not in out and isinstance(v, list) and len(v) == 2:
                try:
                    out[KEYS[k][0]], out[KEYS[k][1]] = int(v[0]), int(v[1])
                except (TypeError, ValueError):
                    pass
    info = (c.get("matchFacts") or {}).get("infoBox") or {}
    out["Referee"] = (info.get("Referee") or {}).get("text")
    return out


def match_stats(match_id):
    data = fetch(f"{FOTMOB}/matchDetails?matchId={match_id}", "fotmob")
    return parse_details(json.loads(data)) if data else None


def row(div, m, st):
    ko = datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))
    r = {"Div": div, "Date": ko.strftime("%d/%m/%Y"), "Time": ko.strftime("%H:%M"), "HomeTeam": m["home"],
         "AwayTeam": m["away"], "FTHG": m["hg"], "FTAG": m["ag"]}
    r.update({k: st.get(k) for k in COLUMNS if k in st})
    return r


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in sorted(rows, key=lambda r: (r["Date"][6:] + r["Date"][3:5] + r["Date"][:2], r["Time"], r["HomeTeam"])):
        w.writerow({k: ("" if r.get(k) is None else r[k]) for k in COLUMNS})
    return buf.getvalue()


def season_rows(div, fotmob_id, seasons, start, end, cache, settle_hours=3, max_new=900, log=None):
    """Rows for matches kicked off in [start, end) from the given FotMob seasons (None = the current one).
    `cache` {fotmob match id: row} is updated in place, so each match's details are fetched once."""
    now = datetime.now(timezone.utc)
    seen, new = set(), 0
    for s in seasons:
        ms = league_matches(fotmob_id, s)
        if ms is None:
            if log is not None:
                log.append(f"FotMob league {fotmob_id} season {s}: download failed")
            continue
        for m in ms:
            if not m["finished"] or not m["kickoff"] or m["fotmob_id"] in seen:
                continue
            ko = datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))
            if not (start <= ko.date() < end) or now - ko < timedelta(hours=settle_hours):
                continue
            seen.add(m["fotmob_id"])
            if m["fotmob_id"] in cache and (cache[m["fotmob_id"]]["FTHG"], cache[m["fotmob_id"]]["FTAG"]) == (m["hg"], m["ag"]):
                continue
            if new >= max_new:
                continue
            st = match_stats(m["fotmob_id"])
            if st is None:
                continue
            cache[m["fotmob_id"]] = row(div, m, st)
            new += 1
    return [r for r in cache.values() if start <= row_date(r) < end], new


def row_date(r):
    return datetime.strptime(r["Date"], "%d/%m/%Y").date()
