"""Model 2 vs model 3, live: which is more accurate on real matches?

  python tools/compare_models.py [--season 2627] [--out data/learning]

Model 2 = the settings frozen on 17 Nov 2026 (data/learning/champion/model2.json), before any self-review change.
Model 3 = the live model (whatever the weekly self-review has changed since). For every estimate the pipeline also
computes model 2 in the shadow (prediction file key "shadow"; "same" while the settings are identical), frozen at
kick-off like the live one, so both are scored on the same matches with the same team news.

Per stat (numbers alone; the subjective view moves both alike):
  miss      |actual - expected total|            (lower is better)
  1x2       Brier score on win/draw/loss (goals)  (lower is better)
  lines     Brier on the fixed lines (LINES)       (lower is better)
  take80    how often the 80% take came true vs the chance given
Paired over the matches where the two differ; z = mean difference / its standard error.
Verdict: "model 3 better" / "model 2 better" when 50+ differing matches and |z| >= 2 (on 1x2 for goals, else miss);
otherwise "too early". While nothing has changed every match is "same", so the two are equal by construction.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from model.core import TAKE_P  # noqa: E402

STATS = ["goals", "corners", "cards", "shots", "shots_on_target"]
MIN_N, MIN_Z = 50, 2.0


def paired(xs):
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else 0.0), 0.0, n
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    if sd == 0:  # every match differs by exactly the same amount: as clear as it gets
        return m, (math.copysign(99.0, m) if m else 0.0), n
    return m, m / (sd / math.sqrt(n)), n


def brier_1x2(s, hg, ag):
    o = (1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if hg < ag else 0.0)
    p = (s.get("home_win", 0), s.get("draw", 0), s.get("away_win", 0))
    return sum((a - b) ** 2 for a, b in zip(p, o))


def lines_brier(s, actual):
    xs = [(p - (1.0 if actual > float(l) else 0.0)) ** 2 for l, p in (s.get("over") or {}).items()]
    return sum(xs) / len(xs) if xs else None


def take_hit(s, actual):
    """(hit, p) of the tightest 80% side, or None (side choice without usual rates; this is about calibration)."""
    c = [{"side": k, **v} for k, v in (s.get("take_line") or {}).items() if v and v.get("p", 0) >= TAKE_P - 1e-9]
    if not c:
        return None
    t = min(c, key=lambda x: (round(x["p"], 9), x["side"] != "over"))
    return (actual > float(t["line"]) if t["side"] == "over" else actual < float(t["line"])), t["p"]


def compare(preds):
    out = {"matches": len(preds), "same": 0, "differ": 0, "stats": {}}
    acc = {st: {"miss": [], "1x2": [], "lines": [], "t2": [0, 0], "t3": [0, 0]} for st in STATS}
    for d in preds:
        sh = d.get("shadow")
        if sh == "same":
            out["same"] += 1
            continue
        if not isinstance(sh, dict):
            continue
        out["differ"] += 1
        live, two, res = d["prediction"]["stats"], sh["stats"], d["result"]
        for st in STATS:
            r, s3, s2 = res.get(st), live.get(st), two.get(st)
            if not r or not s3 or not s2 or r.get("excluded") or r.get("actual_total") is None:
                continue
            a, A = r["actual_total"], acc[st]
            A["miss"].append(abs(a - s2["total"]) - abs(a - s3["total"]))      # > 0: model 3 missed by less
            if st == "goals" and r.get("actual"):
                hg, ag = r["actual"]
                A["1x2"].append(brier_1x2(s2, hg, ag) - brier_1x2(s3, hg, ag))
            b2, b3 = lines_brier(s2, a), lines_brier(s3, a)
            if b2 is not None and b3 is not None:
                A["lines"].append(b2 - b3)
            for key, s in (("t2", s2), ("t3", s3)):
                th = take_hit(s, a)
                if th:
                    A[key][0] += th[0]
                    A[key][1] += 1
    for st, A in acc.items():
        row = {}
        for k in ("miss", "1x2", "lines"):
            if A[k]:
                m, z, n = paired(A[k])
                row[k] = {"model3_gain": round(m, 4), "z": round(z, 2), "n": n}
        for k, lab in (("t2", "take80_model2"), ("t3", "take80_model3")):
            if A[k][1]:
                row[lab] = round(A[k][0] / A[k][1], 3)
        key = row.get("1x2" if st == "goals" else "miss")
        if not key or key["n"] < MIN_N or abs(key["z"]) < MIN_Z:
            row["verdict"] = "too early" if out["differ"] else "identical (no change yet)"
        else:
            row["verdict"] = "model 3 better" if key["z"] > 0 else "model 2 better"
        out["stats"][st] = row
    v = {st: r["verdict"] for st, r in out["stats"].items()}
    m2, m3 = list(v.values()).count("model 2 better"), list(v.values()).count("model 3 better")
    if not out["differ"]:
        out["overall"] = "identical (no change yet)"
    elif v.get("goals") == "model 2 better" or m2 > m3:   # win/draw/loss and goals come first
        out["overall"] = "model 2 better"
    elif m3 > m2:
        out["overall"] = "model 3 better"
    else:
        out["overall"] = "too early"
    return out


def markdown(R):
    L = [f"# Model 2 vs model 3 (live), {R['made_at']}", "",
         f"{R['matches']} scored matches with a shadow: {R['differ']} where the models differ, {R['same']} identical.",
         f"**Overall: {R['overall']}.** (Verdict needs {MIN_N}+ differing matches and |z| >= {MIN_Z:g}; goals are judged on win/draw/loss.)", "",
         "| Stat | Verdict | Miss: model 3 gain (z, n) | Win/draw/loss gain (z) | 80% take came true: model 2 / model 3 |",
         "|---|---|---|---|---|"]
    def cell(x, digits):
        return f"{x['model3_gain']:+.{digits}f} (z {x['z']}, n {x['n']})" if x else "-"
    for st, r in R["stats"].items():
        L.append(f"| {st} | {r['verdict']} | {cell(r.get('miss'), 3)} | {cell(r.get('1x2'), 4)} | "
                 f"{r.get('take80_model2', '-')} / {r.get('take80_model3', '-')} |")
    return "\n".join(L) + "\n"


def load(season):
    out = []
    for f in glob.glob(os.path.join(ROOT, "data", "predictions", season, "*", "*.json")):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        if d.get("result") and "shadow" in d and isinstance(d.get("prediction"), dict) and "stats" in d["prediction"]:
            out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "learning"))
    a = ap.parse_args()
    season = a.season or sorted(os.listdir(os.path.join(ROOT, "data", "predictions")))[-1]
    R = compare(load(season))
    R["made_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    os.makedirs(a.out, exist_ok=True)
    json.dump(R, open(os.path.join(a.out, "model_compare.json"), "w"), indent=1)
    md = markdown(R)
    open(os.path.join(a.out, "model_compare.md"), "w").write(md)
    print(md)


if __name__ == "__main__":
    main()
