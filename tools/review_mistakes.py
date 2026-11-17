"""Mistake review: what the scored estimates got wrong, and whether it is a pattern or noise.

  python tools/review_mistakes.py [--season 2627] [--out data/learning]

Reads every scored (frozen, finished) estimate in data/predictions/<season>/ and writes
data/learning/review_last.json and data/learning/review_last.md. Used by the matchday-self-review skill.

What it measures (all on the numbers alone unless it says "take" or "view"):
  bias        per competition x stat: mean (actual - expected); a steady sign means the level is off
  error       per stat: average miss vs league averages (baseline_error) - is the model still better?
  take80      the highlighted take line (80%+): how often it came true vs the chance it was given
  adjust      did the adjustments help? final number vs the base alone (base = final / (0.45 + 0.55 x factor))
  adjust_kind per adjustment kind (missing, referee, momentum...): did moving the number help when it fired?
  views       subjective views: was the lean (higher/lower) right vs the numbers alone, per stat
  take        our take vs the numbers alone: which missed by less

Every finding gets a verdict from its sample size and strength, so small samples are not mistaken for lessons:
  SIGNAL  n >= 30 and |z| >= 2      (strong enough to act on, through the skill's gates)
  WATCH   n >= 10 and |z| >= 1.5    (note it, act only if it holds at the next review)
  NOISE   anything else             (do nothing)
About 90 findings are checked each time, so a few SIGNALs will be chance: each finding also carries `previous`
(its verdict at the last review) and `held` (SIGNAL now and WATCH/SIGNAL last time, same sign). Only a held
finding is a lesson. Each run is archived in data/learning/history/review_<date>.json.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from model.core import TAKE_P  # noqa: E402

STATS = ["goals", "corners", "cards", "shots", "shots_on_target"]


def verdict(n, z):
    if n >= 30 and abs(z) >= 2:
        return "SIGNAL"
    if n >= 10 and abs(z) >= 1.5:
        return "WATCH"
    return "NOISE"


def mean_z(xs):
    """mean, z of the mean against 0 (t-like), n."""
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else 0.0), 0.0, n
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, (m / (sd / math.sqrt(n)) if sd > 0 else 0.0), n


def rate_z(hits, n, p0):
    """hit rate and z against an expected rate p0 (normal approximation)."""
    if n == 0:
        return 0.0, 0.0
    r = hits / n
    sd = math.sqrt(p0 * (1 - p0) / n) if 0 < p0 < 1 else 0
    return r, ((r - p0) / sd if sd else 0.0)


def take_of(s):
    """The take line that was highlighted for a stat: model take_line + side rule without usual rates
    (tightest, ties to over; review is about calibration, the side choice barely matters), else the shown/fixed lines."""
    tl = s.get("take_line")
    if tl is None:
        tl = {"over": None, "under": None}
        for line, p in (s.get("over_show") or s.get("over") or {}).items():
            for side, q in (("over", p), ("under", 1 - p)):
                if q >= TAKE_P - 1e-9 and (not tl[side] or q < tl[side]["p"]):
                    tl[side] = {"line": line, "p": q}
    c = [{"side": k, **v} for k, v in tl.items() if v]
    if not c:
        return None
    return min(c, key=lambda x: (round(x["p"], 9), x["side"] != "over"))


def load(season):
    out = []
    for f in glob.glob(os.path.join(ROOT, "data", "predictions", season, "*", "*.json")):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        if d.get("result") and isinstance(d.get("prediction"), dict) and "stats" in d["prediction"]:
            out.append(d)
    return sorted(out, key=lambda d: d.get("kickoff", ""))


def review(preds):
    R = {"matches": len(preds), "from": preds[0]["kickoff"][:10] if preds else None,
         "to": preds[-1]["kickoff"][:10] if preds else None, "findings": []}
    F = R["findings"]

    def add(kind, key, n, z, text, **extra):
        F.append({"kind": kind, "key": key, "n": n, "z": round(z, 2), "verdict": verdict(n, z), "text": text, **extra})

    bias = defaultdict(list)
    err = defaultdict(lambda: [[], []])
    take80 = defaultdict(lambda: [0, 0, 0.0])
    adj = defaultdict(list)
    kind_help = defaultdict(list)
    views = defaultdict(lambda: [0, 0])
    takes = defaultdict(list)
    for d in preds:
        P, res, lg = d["prediction"], d["result"], d["league"]
        by = (P.get("recipe") or {}).get("by_stat") or {}
        bw, aw = (P.get("recipe") or {}).get("base_weight", 0.45), (P.get("recipe") or {}).get("adj_weight", 0.55)
        view = P.get("analyst_view") if isinstance(P.get("analyst_view"), dict) else {}
        for st in STATS:
            r, s = res.get(st), P["stats"].get(st)
            if not r or not s or r.get("excluded") or r.get("actual_total") is None:
                continue
            a, e = r["actual_total"], s["total"]
            bias[(lg, st)].append(a - e)
            err[st][0].append(abs(a - e))
            if r.get("baseline_error") is not None:
                err[st][1].append(abs(r["baseline_error"]))
            t = take_of(s)
            if t:
                hit = a > float(t["line"]) if t["side"] == "over" else a < float(t["line"])
                k = take80[st]
                k[0] += hit
                k[1] += 1
                k[2] += t["p"]
            f = (by.get(st) or {}).get("factor")
            if f and len(f) == 2:
                base = s["home"] / (bw + aw * f[0]) + s["away"] / (bw + aw * f[1])
                gain = abs(a - base) - abs(a - e)                     # > 0: adjustments helped
                adj[st].append(gain)
                for kd in {x["kind"] for x in P.get("adjustments", []) if x.get("stat") == st and abs(x.get("effect_pct") or 0) >= 2}:
                    kind_help[(kd, st)].append(gain)
            v = view.get(st) if isinstance(view.get(st), dict) else None
            if v and v.get("lean") in ("higher", "lower") and a != e:
                right = (a > e) == (v["lean"] == "higher")
                views[st][0] += right
                views[st][1] += 1
            tk = ((P.get("take") or {}).get(st) or {}) if P.get("take") else {}
            if tk.get("total") is not None and tk.get("adjust_pct"):
                takes[st].append(abs(a - e) - abs(a - tk["total"]))  # > 0: the take missed by less

    for (lg, st), xs in sorted(bias.items()):
        m, z, n = mean_z(xs)
        add("bias", f"{lg}/{st}", n, z, f"{lg} {st}: actual minus expected averages {m:+.2f} over {n} matches",
            mean=round(m, 3))
    for st, (mine, base) in err.items():
        if mine and base:
            diff = [b - x for x, b in zip(mine, base)]
            m, z, n = mean_z(diff)
            add("error", st, n, z, f"{st}: average miss {sum(mine)/len(mine):.2f} vs league averages {sum(base)/len(base):.2f}"
                f" ({'better' if m > 0 else 'worse'} by {abs(m):.2f} per match)", gain=round(m, 3))
    for st, (h, n, ps) in take80.items():
        if n:
            exp = ps / n
            r, z = rate_z(h, n, exp)
            add("take80", st, n, z, f"{st} 80% take came true {r:.0%} of {n} times (given {exp:.0%} on average)",
                hit_rate=round(r, 3), expected=round(exp, 3))
    for st, xs in adj.items():
        m, z, n = mean_z(xs)
        add("adjust", st, n, z, f"{st}: the adjustments {'helped' if m > 0 else 'hurt'} by {abs(m):.2f} per match vs the base alone",
            gain=round(m, 3))
    for (kd, st), xs in sorted(kind_help.items()):
        m, z, n = mean_z(xs)
        add("adjust_kind", f"{kd}/{st}", n, z, f"{kd} on {st}: when it fired (2%+), the number got {'closer' if m > 0 else 'further'}"
            f" by {abs(m):.2f} per match", gain=round(m, 3))
    for st, (h, n) in views.items():
        r, z = rate_z(h, n, 0.5)
        add("views", st, n, z, f"subjective view on {st}: lean right {h} of {n} ({r:.0%})", hit_rate=round(r, 3))
    for st, xs in takes.items():
        m, z, n = mean_z(xs)
        add("take", st, n, z, f"our take on {st}: missed by {abs(m):.2f} {'less' if m > 0 else 'more'} than the numbers alone",
            gain=round(m, 3))
    order = {"SIGNAL": 0, "WATCH": 1, "NOISE": 2}
    F.sort(key=lambda x: (order[x["verdict"]], -abs(x["z"])))
    return R


def markdown(R, when):
    lines = [f"# Mistake review, {when}", "",
             f"{R['matches']} scored matches ({R['from']} to {R['to']}). SIGNAL = n 30+ and |z| 2+; WATCH = n 10+ and |z| 1.5+.",
             f"Compared with the review of {R.get('compared_with') or 'none (first review, so nothing can have held yet)'}.", ""]
    for v in ("SIGNAL", "WATCH"):
        xs = [f for f in R["findings"] if f["verdict"] == v]
        lines.append(f"## {v} ({len(xs)})")
        lines += [f"- [{f['kind']}] {f['text']} (n={f['n']}, z={f['z']}; last review: {f.get('previous') or 'none'}"
                  f"{'; HELD - a lesson' if f.get('held') else ''})" for f in xs] or ["- none"]
        lines.append("")
    lines.append(f"NOISE: {sum(f['verdict'] == 'NOISE' for f in R['findings'])} findings (in review_last.json).")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "learning"))
    a = ap.parse_args()
    season = a.season or sorted(os.listdir(os.path.join(ROOT, "data", "predictions")))[-1]
    R = review(load(season))
    prev_path = os.path.join(a.out, "review_last.json")
    # compare with the newest archived review at least 5 days old, so re-running in the same week never
    # compares a week with itself (which would mark every SIGNAL as held)
    today = datetime.now(timezone.utc).date()
    older = [f for f in sorted(glob.glob(os.path.join(a.out, "history", "review_*.json")))
             if (today - datetime.strptime(os.path.basename(f)[7:17], "%Y-%m-%d").date()).days >= 5]
    try:
        base = json.load(open(older[-1])) if older else {}
    except (OSError, ValueError):
        base = {}
    prev = {(f["kind"], f["key"]): f for f in base.get("findings", [])}
    R["compared_with"] = base.get("made_at")
    for f in R["findings"]:
        p = prev.get((f["kind"], f["key"]))
        f["previous"] = p["verdict"] if p else None
        f["held"] = bool(p and f["verdict"] == "SIGNAL" and p["verdict"] in ("SIGNAL", "WATCH")
                         and (p["z"] > 0) == (f["z"] > 0))
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    R["season"], R["made_at"] = season, when
    os.makedirs(os.path.join(a.out, "history"), exist_ok=True)
    json.dump(R, open(prev_path, "w"), indent=1)
    json.dump(R, open(os.path.join(a.out, "history", f"review_{when[:10]}.json"), "w"), indent=1)
    md = markdown(R, when)
    open(os.path.join(a.out, "review_last.md"), "w").write(md)
    print(md)


if __name__ == "__main__":
    main()
