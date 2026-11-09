"""Runs in GitHub Actions. Referee of every match in our competitions, from FotMob.

  python tools/collect_referees.py --probe
  python tools/collect_referees.py 2025-07-01 2026-07-01     writes data/history/referees_<from>_<to>.json
  python tools/collect_referees.py 2025-07-01 2026-07-01 --leagues segunda-division:140,super-lig:71 --tag new
      only those leagues (key:FotMob id); writes data/history/referees_<from>_<to>_<tag>.json
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.sources import FOTMOB, FOTMOB_LEAGUE, fetch  # noqa: E402

IDS = {v: k for k, v in FOTMOB_LEAGUE.items()}


def day_matches(d):
    data = fetch(f"{FOTMOB}/matches?date={d.strftime('%Y%m%d')}", "fotmob")
    if not data:
        return []
    out = []
    for L in json.loads(data).get("leagues", []):
        lg = IDS.get(L.get("primaryId"))
        if not lg:
            continue
        for m in L.get("matches", []):
            st = m.get("status") or {}
            out.append({"fotmob_id": m["id"], "league": lg, "home": m["home"]["name"], "away": m["away"]["name"],
                        "hg": m["home"].get("score"), "ag": m["away"].get("score"), "kickoff": st.get("utcTime"),
                        "finished": bool(st.get("finished"))})
    return out


def details(mid):
    data = fetch(f"{FOTMOB}/matchDetails?matchId={mid}", "fotmob")
    if not data:
        return None
    d = json.loads(data)
    info = ((d.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}
    ref = info.get("Referee") or {}
    return {"referee": ref.get("text"), "referee_country": ref.get("country")}


def main():
    os.makedirs("data/history", exist_ok=True)
    if "--probe" in sys.argv:
        rep = {}
        for d in (date(2025, 10, 25), date(2026, 11, 1), date(2026, 11, 8)):
            ms = day_matches(d)
            rep[str(d)] = {"matches": len(ms), "leagues": sorted({m["league"] for m in ms})}
            for m in ms[:3]:
                rep[str(d)].setdefault("examples", []).append({**m, **(details(m["fotmob_id"]) or {})})
        os.makedirs("probe", exist_ok=True)
        json.dump(rep, open("probe/referees.json", "w"), indent=1)
        print(json.dumps(rep, indent=1))
        return
    args = sys.argv[1:]
    tag = ""
    if "--leagues" in args:
        i = args.index("--leagues")
        IDS.clear()
        IDS.update({int(x.split(":")[1]): x.split(":")[0] for x in args[i + 1].split(",")})
        del args[i:i + 2]
    if "--tag" in args:
        i = args.index("--tag")
        tag = "_" + args[i + 1]
        del args[i:i + 2]
    start, end = date.fromisoformat(args[0]), date.fromisoformat(args[1])
    out, d = [], start
    while d < min(end, date.today()):
        for m in day_matches(d):
            if m["finished"]:
                det = details(m["fotmob_id"]) or {}
                out.append({**m, **det})
        d += timedelta(days=1)
        if d.day == 1:
            print(d, len(out), flush=True)
    path = f"data/history/referees_{start.isoformat()}_{end.isoformat()}{tag}.json"
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print(f"{len(out)} matches, {sum(1 for m in out if m.get('referee'))} with a referee -> {path}")


if __name__ == "__main__":
    main()
