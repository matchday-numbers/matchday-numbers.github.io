"""Runs in GitHub Actions: checks every source for the Segunda Division, Super Lig and MLS.
Saves Segunda history CSVs (football-data.co.uk) and writes probe/new_leagues.json.
Usage: python tools/probe_new_leagues.py"""
import csv
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
os.makedirs("probe", exist_ok=True)
os.makedirs("data/history", exist_ok=True)
ESPN = {"segunda-division": "esp.2", "super-lig": "tur.1", "mls": "usa.1"}
FOTMOB = {"segunda-division": 140, "super-lig": 71, "mls": 130}
report = {"_fd": {}, "_espn": {}, "_fotmob": {}}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = r.read()
                if d[:2] == b"\x1f\x8b":
                    d = gzip.decompress(d)
                time.sleep(0.2)
                return r.status, d
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                return f"ERR {e!r}"[:80], b""
            time.sleep(2)


def fd_summary(text):
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    cols = list(rows[0].keys()) if rows else []
    def cov(c):
        return sum(1 for r in rows if (r.get(c) or "").strip()) if c in cols else None
    return {"rows": len(rows), "has": {c: cov(c) for c in ("HS", "HST", "HC", "HY", "HR", "Referee")},
            "first": rows[0].get("Date") if rows else None, "last": rows[-1].get("Date") if rows else None,
            "cols": cols[:40]}


# ---------------------------------------------------------------- football-data.co.uk
for s in ["2122", "2223", "2324", "2425", "2526", "2627"]:
    st, d = get(f"https://www.football-data.co.uk/mmz4281/{s}/SP2.csv")
    if st == 200 and d:
        text = d.decode("utf-8-sig", errors="replace")
        report["_fd"][f"SP2_{s}"] = fd_summary(text)
        if s != "2627":
            with open(f"data/history/segunda-division_{s}.csv", "w") as f:
                f.write(text)
    else:
        report["_fd"][f"SP2_{s}"] = {"status": st}
st, d = get("https://www.football-data.co.uk/mmz4281/2627/T1.csv")
report["_fd"]["T1_2627"] = fd_summary(d.decode("utf-8-sig", errors="replace")) if st == 200 and d else {"status": st}
st, d = get("https://www.football-data.co.uk/new/USA.csv")
if st == 200 and d:
    rows = list(csv.DictReader(io.StringIO(d.decode("utf-8-sig", errors="replace"))))
    report["_fd"]["USA"] = {"rows": len(rows), "cols": list(rows[0].keys())[:30] if rows else [],
                            "seasons": sorted({r.get("Season") for r in rows})[-4:]}
else:
    report["_fd"]["USA"] = {"status": st}

# ---------------------------------------------------------------- ESPN
E = "https://site.api.espn.com/apis/site/v2/sports/soccer"
for lg, code in ESPN.items():
    r = report["_espn"].setdefault(lg, {})
    for month in ["202610", "202611", "202612", "202602", "202503", "202409"]:
        st, d = get(f"{E}/{code}/scoreboard?dates={month}&limit=500")
        ev = json.loads(d).get("events", []) if st == 200 and d else []
        done = [e for e in ev if e["status"]["type"].get("completed")]
        r[month] = {"status": st, "events": len(ev), "completed": len(done),
                    "first": ev[0]["date"] if ev else None, "last": ev[-1]["date"] if ev else None,
                    "notes": sorted({n.get("headline") for e in ev for n in e["competitions"][0].get("notes", []) if n.get("headline")})[:6],
                    "season_types": sorted({str((e.get("season") or {}).get("type")) + ":" + str((e.get("season") or {}).get("slug")) for e in ev})[:6]}
        if done and "box" not in r:
            st2, d2 = get(f"{E}/{code}/summary?event={done[-1]['id']}")
            if st2 == 200:
                s = json.loads(d2)
                teams = s.get("boxscore", {}).get("teams", [])
                r["box"] = {"month": month, "event": done[-1]["id"],
                            "stats": {t["team"]["displayName"]: {x["name"]: x.get("displayValue") for x in t.get("statistics", [])
                                                                 if x["name"] in ("wonCorners", "yellowCards", "redCards", "totalShots", "shotsOnTarget", "foulsCommitted")}
                                      for t in teams},
                            "rosters": sum(len(x.get("roster", [])) for x in s.get("rosters", [])),
                            "key_events": len(s.get("keyEvents") or [])}
    # an older finished match (backtest seasons)
    st, d = get(f"{E}/{code}/scoreboard?dates={'20250405' if lg == 'mls' else '20250405'}")
    ev = [e for e in (json.loads(d).get("events", []) if st == 200 and d else []) if e["status"]["type"].get("completed")]
    if ev:
        st2, d2 = get(f"{E}/{code}/summary?event={ev[0]['id']}")
        if st2 == 200:
            teams = json.loads(d2).get("boxscore", {}).get("teams", [])
            r["old_box"] = {t["team"]["displayName"]: {x["name"]: x.get("displayValue") for x in t.get("statistics", [])
                                                     if x["name"] in ("wonCorners", "yellowCards", "totalShots", "shotsOnTarget")} for t in teams}
    st, d = get(f"https://site.api.espn.com/apis/v2/sports/soccer/{code}/standings")
    if st == 200 and d:
        s = json.loads(d)
        r["standings_groups"] = [c.get("name") for c in s.get("children", [])][:4]

# ---------------------------------------------------------------- FotMob
F = "https://www.fotmob.com/api/data"
for lg, fid in FOTMOB.items():
    r = report["_fotmob"].setdefault(lg, {})
    for q in [f"leagues?id={fid}", f"leagues?id={fid}&season=2025", f"leagues?id={fid}&season=2025%2F2026"]:
        st, d = get(f"{F}/{q}")
        info = {"status": st}
        if st == 200 and d:
            try:
                j = json.loads(d)
                fx = (j.get("fixtures") or {}).get("allMatches") or j.get("matches", {}).get("allMatches") or []
                info.update({"keys": list(j.keys())[:20], "matches": len(fx),
                             "finished": sum(1 for m in fx if (m.get("status") or {}).get("finished")),
                             "first": (fx[0].get("status") or {}).get("utcTime") if fx else None,
                             "last": (fx[-1].get("status") or {}).get("utcTime") if fx else None,
                             "sample": fx[0] if fx else None,
                             "seasons": [x for x in (j.get("allAvailableSeasons") or [])][:6]})
                if fx and "detail" not in r:
                    fin = [m for m in fx if (m.get("status") or {}).get("finished")]
                    if fin:
                        mid = fin[-1]["id"]
                        st2, d2 = get(f"{F}/matchDetails?matchId={mid}")
                        if st2 == 200:
                            md = json.loads(d2)
                            c = md.get("content") or {}
                            per = ((c.get("stats") or {}).get("Periods") or {}).get("All") or {}
                            flat = []
                            for g in per.get("stats", []) or []:
                                for x in g.get("stats", []) or []:
                                    flat.append([g.get("key") or g.get("title"), x.get("key"), x.get("title"), x.get("stats")])
                            r["detail"] = {"match": mid, "general": {k: (md.get("general") or {}).get(k) for k in ("homeTeam", "awayTeam", "leagueName", "matchTimeUTCDate")},
                                           "header": (md.get("header") or {}).get("status", {}).get("scoreStr"),
                                           "referee": (((c.get("matchFacts") or {}).get("infoBox") or {}).get("Referee") or {}).get("text"),
                                           "stats": flat[:60]}
            except Exception as e:  # noqa: BLE001
                info["error"] = repr(e)[:200]
        r[q] = info

with open("probe/new_leagues.json", "w") as f:
    json.dump(report, f, indent=1, default=str)
print(json.dumps({k: (list(v) if isinstance(v, dict) else v) for k, v in report.items()}))
