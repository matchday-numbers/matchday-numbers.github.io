"""Downloads from the free sources.

football-data.co.uk  curated per-season CSVs: results, shots, corners, cards, referee (PL), xG.
ESPN public JSON     the feed behind espn.com: fixtures, results, team stats, lineups, goals.
FotMob public JSON   team news and referees; match stats for MLS (football-data.co.uk has MLS results only).
                     ESPN and FotMob are unofficial: if a format changes, the run logs it and keeps the last good data.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
FD = "https://www.football-data.co.uk"

# kind "domestic": estimates + cross-checked stats; kind "europe": stats only (teams from different leagues)
LEAGUES = {
    "premier-league": {"name": "Premier League", "short": "Premier League", "espn": "eng.1", "fd": "E0", "fotmob": 47, "country": "England", "kind": "domestic"},
    "la-liga": {"name": "La Liga", "short": "La Liga", "espn": "esp.1", "fd": "SP1", "fotmob": 87, "country": "Spain", "kind": "domestic"},
    "serie-a": {"name": "Serie A", "short": "Serie A", "espn": "ita.1", "fd": "I1", "fotmob": 55, "country": "Italy", "kind": "domestic"},
    "bundesliga": {"name": "Bundesliga", "short": "Bundesliga", "espn": "ger.1", "fd": "D1", "fotmob": 54, "country": "Germany", "kind": "domestic"},
    "ligue-1": {"name": "Ligue 1", "short": "Ligue 1", "espn": "fra.1", "fd": "F1", "fotmob": 53, "country": "France", "kind": "domestic"},
    "eredivisie": {"name": "Eredivisie", "short": "Eredivisie", "espn": "ned.1", "fd": "N1", "fotmob": 57, "country": "Netherlands", "kind": "domestic"},
    "primeira-liga": {"name": "Primeira Liga", "short": "Primeira", "espn": "por.1", "fd": "P1", "fotmob": 61, "country": "Portugal", "kind": "domestic"},
    "super-lig": {"name": "Süper Lig", "short": "Süper Lig", "espn": "tur.1", "fd": "T1", "fotmob": 71, "country": "Turkey", "kind": "domestic"},
    "segunda-division": {"name": "Segunda División", "short": "Segunda", "espn": "esp.2", "fd": "SP2", "fotmob": 140, "country": "Spain", "kind": "domestic"},
    # MLS: football-data.co.uk has results only, so FotMob is the first stats source (pipeline/fotmob_stats.py)
    "mls": {"name": "MLS", "short": "MLS", "espn": "usa.1", "fd": None, "stats": "fotmob", "fd_div": "USA", "fotmob": 130, "country": "USA", "kind": "domestic"},
    "champions-league": {"name": "Champions League", "short": "UCL", "espn": "uefa.champions", "fd": None, "fotmob": 42, "country": "Europe", "kind": "europe"},
    "europa-league": {"name": "Europa League", "short": "UEL", "espn": "uefa.europa", "fd": None, "fotmob": 73, "country": "Europe", "kind": "europe"},
    "conference-league": {"name": "Conference League", "short": "UECL", "espn": "uefa.europa.conf", "fd": None, "fotmob": 10216, "country": "Europe", "kind": "europe"},
}
DOMESTIC = [k for k, v in LEAGUES.items() if v["kind"] == "domestic"]
# leagues whose estimates passed the backtest (beat league averages on win/draw/loss and goals in 2025-26,
# see backtest/results.json "by_league"); a league that fails is removed here and shows stats only
# (Super Lig, Segunda Division and MLS, added Nov 2026: backtest/results_recipe.json "by_comp"; they beat the
# average on win/draw/loss and goals in both 2024-25 and 2025-26)
PREDICTED = list(DOMESTIC) + ["champions-league", "europa-league", "conference-league"]
# leagues whose first stats source is FotMob rather than football-data.co.uk
FOTMOB_STATS = [k for k, v in LEAGUES.items() if v.get("stats") == "fotmob"]
# leagues with no clubs in Europe: left out of the all-competition fit used for European games
JOINT_SKIP = {"segunda-division", "mls"}
EUROPE = [k for k, v in LEAGUES.items() if v["kind"] == "europe"]
FOTMOB = "https://www.fotmob.com/api/data"
FOTMOB_LEAGUE = {k: v["fotmob"] for k, v in LEAGUES.items()}

CALLS = {"espn": 0, "fd": 0, "fotmob": 0, "errors": []}


def fetch(url, kind, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                CALLS[kind] += 1
                time.sleep(0.15)
                return data
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (400, 404):
                CALLS["errors"].append(f"{e.code} {url}")
                return None
            if attempt == retries - 1:
                CALLS["errors"].append(f"{type(e).__name__} {url}: {e}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


# ---------------------------------------------------------------- football-data.co.uk
def season_code(d: datetime):
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def fd_results_csv(league, season):
    code = LEAGUES[league]["fd"]
    data = fetch(f"{FD}/mmz4281/{season}/{code}.csv", "fd")
    return data.decode("utf-8-sig", errors="replace") if data else None


def fd_fixtures_csv():
    data = fetch(f"{FD}/fixtures.csv", "fd")
    return data.decode("utf-8-sig", errors="replace") if data else None


# ---------------------------------------------------------------- ESPN
def espn_scoreboard(league, when):
    """All events of one day (YYYYMMDD) or one month (YYYYMM) for a league."""
    data = fetch(f"{ESPN}/{LEAGUES[league]['espn']}/scoreboard?dates={when}&limit=500", "espn")
    if not data:
        return None
    return [parse_event(e) for e in json.loads(data).get("events", [])]


def _team(c):
    t = c.get("team", {})
    logo = t.get("logo") or (t.get("logos") or [{}])[0].get("href")
    return {"espn_id": t.get("id"), "name": t.get("displayName"), "short": t.get("shortDisplayName") or t.get("displayName"),
            "abbr": t.get("abbreviation"), "logo": logo, "color": t.get("color"), "alt_color": t.get("alternateColor")}


def parse_event(e):
    comp = e["competitions"][0]
    cs = {c["homeAway"]: c for c in comp["competitors"]}
    st = e["status"]["type"]
    out = {
        "espn_id": e["id"], "kickoff": e["date"], "status": st.get("state"), "completed": bool(st.get("completed")),
        "status_detail": st.get("description"),
        "home": _team(cs["home"]), "away": _team(cs["away"]),
        "venue": (comp.get("venue") or {}).get("fullName"),
        "season_year": (e.get("season") or {}).get("year"), "season_slug": (e.get("season") or {}).get("slug"),
    }
    if out["completed"]:
        out["hg"] = int(cs["home"].get("score") or 0)
        out["ag"] = int(cs["away"].get("score") or 0)
    round_note = [n.get("headline") for n in comp.get("notes", []) if n.get("headline")]
    if round_note:
        out["round"] = round_note[0]
    return out


def _minute(clock):
    s = (clock or {}).get("displayValue") or ""
    s = s.split("'")[0].strip()
    try:
        return int(s.split("+")[0])
    except ValueError:
        v = (clock or {}).get("value")
        return int(v // 60) if v else None


def espn_summary(league, event_id):
    data = fetch(f"{ESPN}/{LEAGUES[league]['espn']}/summary?event={event_id}", "espn")
    if not data:
        return None
    return parse_summary(json.loads(data))


STAT_MAP = {"wonCorners": "corners", "yellowCards": "yellow", "redCards": "red", "totalShots": "shots",
            "shotsOnTarget": "sot", "foulsCommitted": "fouls", "possessionPct": "possession"}


def parse_summary(s):
    """Team stats, lineups with minutes, goals and cards from a finished match."""
    hc = s["header"]["competitions"][0]
    side_of = {c["team"]["id"]: c["homeAway"] for c in hc["competitors"]}
    teams = {}
    for t in s.get("boxscore", {}).get("teams", []):
        side = side_of.get(t["team"]["id"])
        vals = {}
        for x in t.get("statistics", []):
            if x["name"] in STAT_MAP:
                try:
                    vals[STAT_MAP[x["name"]]] = float(x["displayValue"])
                except (TypeError, ValueError):
                    pass
        teams[side] = vals
    events = s.get("keyEvents") or []
    end = 120 if any("extra" in (k.get("type", {}).get("type") or "") for k in events) else 90
    subs_in, subs_out, sent_off = {}, {}, {}
    goals, cards = [], []
    for k in events:
        typ = (k.get("type", {}).get("type") or "").lower()
        names = [p["athlete"]["displayName"] for p in k.get("participants", []) if p.get("athlete")]
        team = (k.get("team") or {}).get("displayName")
        minute = _minute(k.get("clock"))
        if typ == "substitution" and len(names) >= 2:
            subs_in[names[0]] = minute
            subs_out[names[1]] = minute
        elif k.get("scoringPlay"):
            goals.append({"minute": minute, "team": team, "scorer": names[0] if names else None,
                          "assist": names[1] if len(names) > 1 else None,
                          "own_goal": "own" in typ, "penalty": "penalty" in typ})
        elif "yellow" in typ or "red" in typ:
            red = "red" in typ
            cards.append({"minute": minute, "team": team, "player": names[0] if names else None,
                          "card": "red" if red else "yellow", "second_yellow": "yellow" in typ and red})
            if red and names:
                sent_off[names[0]] = minute
    lineups = {}
    for r in s.get("rosters", []):
        side = r.get("homeAway")
        players = []
        for p in r.get("roster", []):
            name = p["athlete"]["displayName"]
            st = {x["name"]: x.get("value") for x in p.get("stats", [])}
            if p.get("starter"):
                start = 0
            elif p.get("subbedIn"):
                start = subs_in.get(name)
            else:
                start = None
            mins = 0
            if start is not None:
                stop = min(x for x in (subs_out.get(name), sent_off.get(name), end) if x is not None)
                mins = max(stop - start, 1)
            players.append({"id": p["athlete"].get("id"), "name": name,
                            "pos": (p.get("position") or {}).get("abbreviation"),
                            "starter": bool(p.get("starter")), "minutes": mins,
                            "goals": int(st.get("totalGoals") or 0), "assists": int(st.get("goalAssists") or 0),
                            "yellow": int(st.get("yellowCards") or 0), "red": int(st.get("redCards") or 0)})
        lineups[side] = {"formation": r.get("formation"), "players": players}
    return {"teams": teams, "lineups": lineups, "goals": goals, "cards": cards,
            "venue": (s.get("gameInfo", {}).get("venue") or {}).get("fullName"),
            "attendance": s.get("gameInfo", {}).get("attendance")}


def espn_team_last_match(team_espn_id, before_iso):
    """Most recent finished match in ANY competition before a time (for rest days)."""
    data = fetch(f"{ESPN}/all/teams/{team_espn_id}/schedule", "espn")
    if not data:
        return None
    best = None
    for e in json.loads(data).get("events", []):
        if e["date"] < before_iso and (best is None or e["date"] > best[0]):
            league = (e.get("league") or {}).get("name") or ""
            best = (e["date"], league)
    return best


# ---------------------------------------------------------------- FotMob (team news only)
def fotmob_day(day):
    """League matches on a day (YYYYMMDD): [{fotmob_id, league, home, away, kickoff}]."""
    data = fetch(f"{FOTMOB}/matches?date={day}", "fotmob")
    if not data:
        return None
    out = []
    ids = {v: k for k, v in FOTMOB_LEAGUE.items()}
    for L in json.loads(data).get("leagues", []):
        lg = ids.get(L.get("primaryId"))
        if not lg:
            continue
        for m in L.get("matches", []):
            out.append({"fotmob_id": m["id"], "league": lg, "home": m["home"]["name"], "away": m["away"]["name"],
                        "kickoff": (m.get("status") or {}).get("utcTime")})
    return out


def fotmob_unavailable(match_id):
    """{'home': [...], 'away': [...], 'referee': str|None} from FotMob's match page data."""
    data = fetch(f"{FOTMOB}/matchDetails?matchId={match_id}", "fotmob")
    if not data:
        return None
    d = json.loads(data)
    lu = (d.get("content") or {}).get("lineup") or {}
    info = ((d.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}
    out = {"referee": (info.get("Referee") or {}).get("text")}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team = lu.get(key)
        if team is None:
            out[side] = None
            continue
        out[side] = [{"name": u.get("name"), "type": (u.get("unavailability") or {}).get("type"),
                      "expected_return": (u.get("unavailability") or {}).get("expectedReturn")}
                     for u in team.get("unavailable") or []]
    return out


def espn_team_schedule(team_id, season_year):
    """Every match of a club in one season (all competitions), results only."""
    data = fetch(f"{ESPN}/all/teams/{team_id}/schedule?season={season_year}", "espn")
    if not data:
        return None
    out = []
    for e in json.loads(data).get("events", []):
        comp = e["competitions"][0]
        st = (comp.get("status") or e.get("status") or {}).get("type", {})
        cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in cs or "away" not in cs:
            continue

        def score(c):
            v = c.get("score")
            if isinstance(v, dict):
                v = v.get("value", v.get("displayValue"))
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None
        lg = e.get("league") or {}
        out.append({"id": e["id"], "date": e["date"], "league": lg.get("slug") or lg.get("abbreviation"),
                    "completed": bool(st.get("completed")),
                    "home": {"id": cs["home"]["team"]["id"], "name": cs["home"]["team"].get("displayName")},
                    "away": {"id": cs["away"]["team"]["id"], "name": cs["away"]["team"].get("displayName")},
                    "hg": score(cs["home"]), "ag": score(cs["away"])})
    return out


def now_utc():
    return datetime.now(timezone.utc)
