"""Briefs for the subjective view: every posted match (upcoming, with an estimate) that needs one.

  python tools/analyst_briefs.py OUTDIR [--max 60] [--refresh-hours 36] [--stale-hours 18] [--redo-days 5] [--batch 30]

Writes OUTDIR/batch_XX.json (one competition per batch, at most --batch matches each) and prints a summary.
A view is a judgement on the news of the day, so it is redone as news changes. Priority:
  (A) kick-off within --refresh-hours and the view is missing or older than --stale-hours (team news, referee)
  (B) no view at all (every posted match gets one), earliest kick-off first
  (C) kick-off within 7 days and the view is 2+ days old (fresh look at the week's news)
  (D) view older than --redo-days (fresh look at form, injuries and context), earliest kick-off first
Rules: tools/analyst_rules.md.
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS = ["goals", "corners", "cards", "shots", "shots_on_target"]
LABEL = {"goals": "goals", "corners": "corners", "cards": "cards", "shots": "shots", "shots_on_target": "shots on target"}


def jload(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def our_call(stat, s):
    """Same rule as the site: the tightest line the numbers still give 60% or more."""
    backed = [(p if p >= 0.5 else 1 - p, f"{'over' if p >= 0.5 else 'under'} {line}") for line, p in (s.get("over") or {}).items()]
    backed = sorted(x for x in backed if x[0] >= 0.6)
    lab = LABEL[stat]
    if backed:
        return f"{backed[0][1]} {lab} ({round(backed[0][0] * 100)}%)"
    return "close call (no line at 60% or more)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--refresh-hours", type=float, default=36)
    ap.add_argument("--stale-hours", type=float, default=18)
    ap.add_argument("--redo-days", type=float, default=5)
    ap.add_argument("--batch", type=int, default=30)
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    meta = jload(os.path.join(ROOT, "site", "data", "meta.json"), {})
    season = meta.get("season")
    views = jload(os.path.join(ROOT, "data", "overrides", "analyst.json"), {}).get("matches", {})
    need = []
    for lg in meta.get("leagues", []):
        L = jload(os.path.join(ROOT, "site", "data", f"league-{lg['key']}.json"), {})
        pos = {r["team"]["slug"]: r for r in L.get("table", [])}
        for u in L.get("upcoming", []):
            if not u.get("prediction"):
                continue
            ko = ts(u["kickoff"])
            if ko <= now:
                continue
            v = views.get(u["id"])
            hours = (ko - now).total_seconds() / 3600
            age = (now - ts(v["written_at"])).total_seconds() / 3600 if v and v.get("written_at") else None
            if hours <= a.refresh_hours and (v is None or age is None or age >= a.stale_hours):
                prio = 0
            elif v is None:
                prio = 1
            elif age is None or (hours <= 7 * 24 and age >= 48):
                prio = 2
            elif age >= a.redo_days * 24:
                prio = 3
            else:
                continue
            p = jload(os.path.join(ROOT, "data", "predictions", season, lg["key"], f"{u['id']}.json"), None)
            if not p:
                continue
            P = p["prediction"]

            def team_line(t):
                r = pos.get(t["slug"])
                return f"{t['name']}: {ordinal(r['pos'])} of {len(pos)}, {r['pts']} pts from {r['p']} games, last 5 {r['form'] or '-'}" if r else t["name"]
            numbers = {}
            for s in STATS:
                x = P["stats"][s]
                numbers[s] = {"expected": round(x["total"], 1), "home": round(x["home"], 1), "away": round(x["away"], 1),
                              "our_call": our_call(s, x)}
            g = P["stats"]["goals"]
            flags = [f"{a_['kind']}: {a_['detail']}" for a_ in P.get("adjustments", []) if a_["kind"] in ("derby", "stakes")]
            need.append((prio, u["kickoff"], lg["key"], {
                "id": u["id"], "competition": lg["name"], "competition_key": lg["key"], "kickoff_utc": u["kickoff"],
                "days_to_kickoff": round(hours / 24, 1), "home": u["home"]["name"], "away": u["away"]["name"],
                "venue": u.get("venue"), "round": u.get("round"),
                "table": [team_line(u["home"]), team_line(u["away"])],
                "win_draw_loss": {"home_win": round(g["home_win"], 2), "draw": round(g["draw"], 2), "away_win": round(g["away_win"], 2)},
                "numbers": numbers,
                "missing": {side: [f"{x['name']} ({x.get('reason') or 'out'})" for x in (p.get("missing") or {}).get(side, [])] for side in ("home", "away")},
                "team_news_included": bool(p.get("team_news")), "referee": p.get("referee"), "flags": flags,
                "current_view_written_at": (v or {}).get("written_at"),
                "current_view": {k: (v or {}).get(k) for k in ("overall", "goals", "corners", "cards", "shots", "shots_on_target")} if v else None,
            }))
    need.sort(key=lambda x: (x[0], x[1]))
    chosen = need[:a.max]
    os.makedirs(a.outdir, exist_ok=True)
    by_comp = defaultdict(list)
    for prio, ko, lg, b in chosen:
        by_comp[lg].append(b)
    n = 0
    for lg, bs in by_comp.items():
        bs.sort(key=lambda b: b["kickoff_utc"])
        k = -(-len(bs) // a.batch)  # equal-sized batches, at most --batch each
        size = -(-len(bs) // k)
        for i in range(0, len(bs), size):
            n += 1
            path = os.path.join(a.outdir, f"batch_{n:02d}_{lg}.json")
            with open(path, "w") as f:
                json.dump({"competition": lg, "written_for": now.isoformat(), "matches": bs[i:i + size]}, f, indent=1, ensure_ascii=False)
            print(f"{path}: {len(bs[i:i + size])} matches")
    print(f"needing a view: {len(need)} (before kick-off {sum(1 for x in need if x[0] == 0)}, new {sum(1 for x in need if x[0] == 1)}, "
          f"this week {sum(1 for x in need if x[0] == 2)}, older {sum(1 for x in need if x[0] == 3)}); "
          f"briefed {len(chosen)} in {n} batches")


if __name__ == "__main__":
    main()
