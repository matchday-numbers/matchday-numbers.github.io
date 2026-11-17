"""Briefs for the subjective view: posted matches kicking off in the next 48 hours that need one.

  python tools/analyst_briefs.py OUTDIR [--max 80] [--window-hours 48] [--refresh-hours 24] [--stale-hours 16] [--batch 20]

Writes OUTDIR/batch_XX.json (one competition per batch, at most --batch matches each) and prints a summary.
Views are written ONLY for matches kicking off within --window-hours (48 h, model/judgement.py JUDGE_HOURS);
matches further out get none. A view moves the site's numbers ("our take"), so it must follow the news. Priority:
  (A) no view yet, or an older view without sizes (adjust_pct), earliest kick-off first
  (B) kick-off within --refresh-hours and the view is older than --stale-hours (team news, referee, lineups)
  (C) view older than --redo-hours (default 30)
Rules: tools/analyst_rules.md.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from model.judgement import JUDGE_HOURS, MAX_PCT  # noqa: E402
from model.core import TAKE_P  # noqa: E402
from model.usual import pick_take, rate  # noqa: E402
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


def our_call(stat, s, usual_comp=None, comp_name="the competition"):
    """Same as the site: the take line, an over or under line with 80%+ chance (model/core.py take_line +
    model/usual.py pick_take; older estimates: the same rule over the shown lines), with how often games in the
    competition do the same."""
    lab = LABEL[stat]
    h = (usual_comp or {}).get(stat)
    cands = s.get("take_line")
    if cands is None:
        cands = {"over": None, "under": None}
        for line, p in (s.get("over_show") or s.get("over") or {}).items():
            for side, q in (("over", p), ("under", 1 - p)):
                if q >= TAKE_P - 1e-9 and (not cands[side] or q < cands[side]["p"]):
                    cands[side] = {"line": line, "p": q, "shown": True}
    tl = pick_take(cands, h)
    if not tl:
        return f"no line at {round(TAKE_P * 100)}% or more"
    out = f"{tl['side']} {tl['line']} {lab} ({round(tl['p'] * 100)}%"
    if h:
        r = rate(h, tl["line"])
        r = r if tl["side"] == "over" else 1 - r
        out += f"; {comp_name} games {'go over' if tl['side'] == 'over' else 'stay under'} {tl['line']} in {round(r * 100)}%"
    return out + ")"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--max", type=int, default=80)
    ap.add_argument("--window-hours", type=float, default=JUDGE_HOURS)
    ap.add_argument("--refresh-hours", type=float, default=24)
    ap.add_argument("--stale-hours", type=float, default=16)
    ap.add_argument("--redo-hours", type=float, default=30)
    ap.add_argument("--batch", type=int, default=20)
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    meta = jload(os.path.join(ROOT, "site", "data", "meta.json"), {})
    season = meta.get("season")
    views = jload(os.path.join(ROOT, "data", "overrides", "analyst.json"), {}).get("matches", {})
    usual_rates = jload(os.path.join(ROOT, "site", "data", "usual.json"), {})  # model/usual.py, written by the pipeline
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
            hours = (ko - now).total_seconds() / 3600
            if hours > a.window_hours:
                continue  # no subjective view until 48 h before kick-off
            v = views.get(u["id"])
            age = (now - ts(v["written_at"])).total_seconds() / 3600 if v and v.get("written_at") else None
            sized = bool(v) and all(isinstance((v.get(s_) or {}).get("adjust_pct"), (int, float)) for s_ in STATS)
            if v is None or not sized or age is None:
                prio = 0
            elif hours <= a.refresh_hours and age >= a.stale_hours:
                prio = 1
            elif age >= a.redo_hours:
                prio = 2
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
                x = P["stats"][s]  # the numbers alone (before any judgement)
                numbers[s] = {"expected": round(x["total"], 1), "home": round(x["home"], 1), "away": round(x["away"], 1),
                              "site_call": our_call(s, x, usual_rates.get(lg["key"]), lg["name"])}
            g = P["stats"]["goals"]
            flags = [f"{a_['kind']}: {a_['detail']}" for a_ in P.get("adjustments", []) if a_["kind"] in ("derby", "stakes")]
            need.append((prio, u["kickoff"], lg["key"], {
                "id": u["id"], "competition": lg["name"], "competition_key": lg["key"], "kickoff_utc": u["kickoff"],
                "hours_to_kickoff": round(hours, 1), "max_adjust_pct": MAX_PCT, "home": u["home"]["name"], "away": u["away"]["name"],
                "venue": u.get("venue"), "round": u.get("round"),
                "table": [team_line(u["home"]), team_line(u["away"])],
                "win_draw_loss": {"home_win": round(g["home_win"], 2), "draw": round(g["draw"], 2), "away_win": round(g["away_win"], 2)},
                "numbers": numbers,
                "missing": {side: [f"{x['name']} ({x.get('reason') or 'out'})" for x in (p.get("missing") or {}).get(side, [])] for side in ("home", "away")},
                "team_news_included": bool(p.get("team_news")), "referee": p.get("referee"), "flags": flags,
                # what the numbers already moved for (missing players, referee, momentum, derby...): never size these again
                "already_counted": [f"{a_['stat']} {a_.get('side') or 'both'} {a_['kind']} {a_['effect_pct']:+.1f}%: {a_.get('detail') or ''}".strip()
                                    for a_ in P.get("adjustments", []) if a_.get("effect_pct")],
                "current_view_written_at": (v or {}).get("written_at"),
                "current_view": {k: (v or {}).get(k) for k in ("overall", "goals", "corners", "cards", "shots", "shots_on_target")} if v else None,
                "current_view_needs_sizes": bool(v) and not sized,
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
    print(f"needing a view (kick-off within {a.window_hours:.0f} h): {len(need)} (new or unsized {sum(1 for x in need if x[0] == 0)}, "
          f"match-day refresh {sum(1 for x in need if x[0] == 1)}, older {sum(1 for x in need if x[0] == 2)}); "
          f"briefed {len(chosen)} in {n} batches")

if __name__ == "__main__":
    main()
