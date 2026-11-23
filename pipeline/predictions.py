"""Make predictions before kick-off, freeze them, and score them after the match."""
from __future__ import annotations

import math

from model import usual
from model.core import STATS, count_probabilities, goal_probabilities, league_means

ROUND = 3


def rnd(x):
    if isinstance(x, float):
        return round(x, ROUND)
    if isinstance(x, dict):
        return {k: rnd(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rnd(v) for v in x]
    return x


def baseline(predictor, cur):
    """What you'd predict knowing nothing about the teams: league averages only."""
    out = {}
    for stat in STATS:
        mh, ma = league_means(cur, predictor.prev, stat, predictor.params)
        if stat == "goals":
            g = goal_probabilities(mh, ma, predictor.params.dc_rho)
            out[stat] = {"total": mh + ma, "home_win": g["home_win"], "draw": g["draw"], "away_win": g["away_win"],
                         "over": g["over"], "btts": g["btts"]}
        else:
            out[stat] = {"total": mh + ma, **count_probabilities(stat, mh, ma, predictor.params.nb_alpha[stat])}
    return out


def make(predictor, fixture, home, away, cur, ctx, made_at, model_version):
    p = predictor.predict(cur, home, away, ctx)
    return rnd({
        "id": fixture["espn_id"], "league": predictor.league, "kickoff": fixture["kickoff"],
        "home": home, "away": away, "made_at": made_at, "model_version": model_version,
        "prediction": p, "baseline": baseline(predictor, cur),
        "missing": {"home": ctx.get("home_missing") or [], "away": ctx.get("away_missing") or []},
        "doubtful": {"home": ctx.get("home_doubtful") or [], "away": ctx.get("away_doubtful") or []},
        "team_news": bool(ctx.get("injuries_known")),
    })


def _ll(p, y):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -math.log(p if y else 1 - p)


STAT_KEYS = {"goals": ("hg", "ag"), "corners": ("hc", "ac"), "cards": ("hcards", "acards"),
             "shots": ("hs", "as"), "shots_on_target": ("hst", "ast")}


def score(pred, match):
    """Compares a frozen prediction with the final match record."""
    res = {}
    for stat, (hk, ak) in STAT_KEYS.items():
        if match.get(hk) is None or match.get(ak) is None:
            res[stat] = {"excluded": True}
            continue
        P = pred["prediction"]["stats"][stat]
        B = pred["baseline"][stat]
        tot = match[hk] + match[ak]
        lines = {}
        for line, p in P["over"].items():
            y = tot > float(line)
            b = B["over"][line]
            lines[line] = {"p_over": p, "over": y, "hit": (p >= 0.5) == y,
                           "brier": (p - y) ** 2, "baseline_brier": (b - y) ** 2}
        r = {"actual": [match[hk], match[ak]], "actual_total": tot, "expected_total": P["total"],
             "error": P["total"] - tot, "baseline_error": B["total"] - tot,
             "in_range": P["range"][0] <= tot <= P["range"][1], "lines": lines}
        if stat == "goals":
            outcome = "home_win" if match[hk] > match[ak] else "draw" if match[hk] == match[ak] else "away_win"
            probs = {k: P[k] for k in ("home_win", "draw", "away_win")}
            bprobs = {k: B[k] for k in ("home_win", "draw", "away_win")}
            r["outcome"] = outcome
            r["p_outcome"] = probs[outcome]
            r["pick_correct"] = max(probs, key=probs.get) == outcome
            r["brier_1x2"] = sum((probs[k] - (k == outcome)) ** 2 for k in probs)
            r["baseline_brier_1x2"] = sum((bprobs[k] - (k == outcome)) ** 2 for k in bprobs)
            yb = match[hk] > 0 and match[ak] > 0
            r["btts"] = {"p": P["btts"], "yes": yb, "hit": (P["btts"] >= 0.5) == yb}
            r["likely_score_hit"] = f"{match[hk]}-{match[ak]}" == P["likely_scores"][0]["score"]
        res[stat] = r
    return rnd(res)


def score_take(pred, match):
    """Scores "our take" (numbers moved by the subjective view) when a judgement was applied; else None."""
    take = (pred.get("prediction") or {}).get("take")
    if not take or not take.get("applied"):
        return None
    stats = {k: {**v, **(take.get(k) or {})} for k, v in pred["prediction"]["stats"].items()}
    return score({**pred, "prediction": {**pred["prediction"], "stats": stats}}, match)


def take_record(scored):
    """Our take against the numbers alone, on the matches where a judgement moved at least one stat."""
    out, n = {}, 0
    for pred in scored:
        rt, rn = pred.get("result_take"), pred.get("result")
        if not rt or not rn:
            continue
        n += 1
        for stat, t in rt.items():
            r = rn.get(stat) or {}
            if t.get("excluded") or r.get("excluded"):
                continue
            a = out.setdefault(stat, {"n": 0, "abs_error_numbers": 0.0, "abs_error_take": 0.0, "brier_numbers": 0.0,
                                      "brier_take": 0.0, "lines": 0})
            a["n"] += 1
            a["abs_error_numbers"] += abs(r["error"])
            a["abs_error_take"] += abs(t["error"])
            for line, d in t["lines"].items():
                a["lines"] += 1
                a["brier_take"] += d["brier"]
                a["brier_numbers"] += r["lines"][line]["brier"]
            if stat == "goals":
                a["brier_1x2_numbers"] = a.get("brier_1x2_numbers", 0.0) + r["brier_1x2"]
                a["brier_1x2_take"] = a.get("brier_1x2_take", 0.0) + t["brier_1x2"]
    for a in out.values():
        k = a["n"]
        a["mae_numbers"], a["mae_take"] = a.pop("abs_error_numbers") / k, a.pop("abs_error_take") / k
        L = a.pop("lines") or 1
        a["brier_numbers"] /= L
        a["brier_take"] /= L
        if "brier_1x2_numbers" in a:
            a["brier_1x2_numbers"] /= k
            a["brier_1x2_take"] /= k
    return rnd({"matches": n, "by_stat": out})


def public_stats(pred):
    """What the site shows for each stat: our take (numbers moved by the subjective view) when there is one."""
    P = pred.get("prediction") or {}
    T = P.get("take") or {}
    return {k: {**v, **(T.get(k) or {})} for k, v in (P.get("stats") or {}).items()}


def match_calls(pred, comp_usual=None):
    """Our calls for one match (owner, 23 Nov 2026): the highlighted over/under line of every stat, as one group.
    Stored in the estimate file on every run until kick-off, so it is frozen with the estimate."""
    applied = bool(((pred.get("prediction") or {}).get("take") or {}).get("applied"))
    return rnd({"view": applied, "stats": usual.calls(public_stats(pred), comp_usual)})


def score_calls(pred, match, comp_usual=None, previous=None):
    """Scores our calls for a match together: each stat's call came true or not, and how many of them did.
    Uses the calls frozen at kick-off (pred["calls"]); estimates made before 23 Nov 2026 have none, so their calls
    are worked out once with the same rule (reconstructed: True) and kept from then on (previous = result_calls).
    A stat the sources disagree on (or missing) is void and not counted."""
    frozen = pred.get("calls")
    if frozen:
        picks, view, recon = frozen.get("stats") or {}, frozen.get("view", False), False
    elif previous and previous.get("reconstructed"):
        picks = {k: {kk: v[kk] for kk in ("side", "line", "p") if kk in v} for k, v in (previous.get("stats") or {}).items()}
        view, recon = previous.get("view", False), True
    else:
        mc = match_calls(pred, comp_usual)
        picks, view, recon = mc["stats"], mc["view"], True
    out, hits, n = {}, 0, 0
    for st, (hk, ak) in STAT_KEYS.items():
        c = picks.get(st)
        if not c:
            continue
        row = {"side": c["side"], "line": c["line"], "p": c["p"]}
        if match.get(hk) is None or match.get(ak) is None:
            row["void"] = True
        else:
            tot = match[hk] + match[ak]
            row["actual"] = tot
            row["hit"] = tot > float(c["line"]) if c["side"] == "over" else tot < float(c["line"])
            n += 1
            hits += int(row["hit"])
        out[st] = row
    res = {"view": view, "n": n, "hits": hits, "stats": out}
    if recon:
        res["reconstructed"] = True
    return rnd(res)


def calls_record(scored, now_iso=None, days=7):
    """Our calls, match by match, summed up: how many came true, how often every call in a match came true, and the
    same split by stat, competition and whether a subjective view moved the numbers. Also the last `days` days."""
    def blank():
        return {"matches": 0, "calls": 0, "hits": 0, "p_sum": 0.0, "all_right": 0}

    tot, recent, by_stat, by_comp, by_view, dist = blank(), blank(), {}, {}, {"view": blank(), "numbers": blank()}, {}
    cutoff = None
    if now_iso:
        from datetime import datetime, timedelta
        cutoff = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=days)).isoformat()[:16]

    def add(a, rc):
        a["matches"] += 1
        a["calls"] += rc["n"]
        a["hits"] += rc["hits"]
        a["p_sum"] += sum(v["p"] for v in rc["stats"].values() if not v.get("void"))
        a["all_right"] += int(rc["hits"] == rc["n"])

    for pred in scored:
        rc = pred.get("result_calls")
        if not rc or not rc.get("n"):
            continue
        add(tot, rc)
        if cutoff and pred["kickoff"][:16] >= cutoff:
            add(recent, rc)
        add(by_comp.setdefault(pred["league"], blank()), rc)
        add(by_view["view" if rc.get("view") else "numbers"], rc)
        k = f'{rc["hits"]}/{rc["n"]}'
        dist[k] = dist.get(k, 0) + 1
        for st, v in rc["stats"].items():
            if v.get("void"):
                continue
            b = by_stat.setdefault(st, {"calls": 0, "hits": 0, "p_sum": 0.0})
            b["calls"] += 1
            b["hits"] += int(v["hit"])
            b["p_sum"] += v["p"]

    def fin(a):
        c = a.pop("calls") if "calls" in a else 0
        out = {**a, "calls": c}
        ps = out.pop("p_sum")
        out["hit_rate"] = out["hits"] / c if c else None
        out["claimed"] = ps / c if c else None
        if "matches" in out:
            out["all_right_rate"] = out["all_right"] / out["matches"] if out["matches"] else None
        return out

    return rnd({"days": days, **fin(tot), "recent": fin(recent),
                "by_stat": {k: fin(v) for k, v in by_stat.items()},
                "by_comp": {k: fin(v) for k, v in by_comp.items()},
                "by_view": {k: fin(v) for k, v in by_view.items()},
                "distribution": dist})


def aggregate(scored):
    """Track record: per league and stat, plus calibration of every probability."""
    out = {}
    bins = [{"lo": i / 10, "hi": (i + 1) / 10, "n": 0, "p": 0.0, "hits": 0} for i in range(10)]
    for pred in scored:
        lg = pred["league"]
        for stat, r in pred["result"].items():
            if r.get("excluded"):
                continue
            for key in (lg, "all"):
                a = out.setdefault(key, {}).setdefault(stat, {"n": 0, "abs_error": 0.0, "baseline_abs_error": 0.0,
                                                               "in_range": 0, "lines": {}})
                a["n"] += 1
                a["abs_error"] += abs(r["error"])
                a["baseline_abs_error"] += abs(r["baseline_error"])
                a["in_range"] += int(r["in_range"])
                for line, d in r["lines"].items():
                    L = a["lines"].setdefault(line, {"n": 0, "hits": 0, "brier": 0.0, "baseline_brier": 0.0})
                    L["n"] += 1
                    L["hits"] += int(d["hit"])
                    L["brier"] += d["brier"]
                    L["baseline_brier"] += d["baseline_brier"]
                if stat == "goals":
                    a.setdefault("picks", 0)
                    a["picks"] = a.get("picks", 0) + int(r["pick_correct"])
                    a["brier_1x2"] = a.get("brier_1x2", 0.0) + r["brier_1x2"]
                    a["baseline_brier_1x2"] = a.get("baseline_brier_1x2", 0.0) + r["baseline_brier_1x2"]
                    a["btts_hits"] = a.get("btts_hits", 0) + int(r["btts"]["hit"])
                    a["score_hits"] = a.get("score_hits", 0) + int(r["likely_score_hit"])
            probs = [(d["p_over"], d["over"]) for d in r["lines"].values()]
            if stat == "goals":
                P = pred["prediction"]["stats"]["goals"]
                probs += [(P[k], r["outcome"] == k) for k in ("home_win", "draw", "away_win")]
            for p, y in probs:
                b = bins[min(int(p * 10), 9)]
                b["n"] += 1
                b["p"] += p
                b["hits"] += int(y)
    for lg in out.values():
        for a in lg.values():
            n = a["n"]
            a["mae"] = a.pop("abs_error") / n
            a["baseline_mae"] = a.pop("baseline_abs_error") / n
            a["in_range_rate"] = a.pop("in_range") / n
            for L in a["lines"].values():
                L["hit_rate"] = L.pop("hits") / L["n"]
                L["brier"] /= L["n"]
                L["baseline_brier"] /= L["n"]
            if "picks" in a:
                a["pick_rate"] = a.pop("picks") / n
                a["brier_1x2"] /= n
                a["baseline_brier_1x2"] /= n
                a["btts_rate"] = a.pop("btts_hits") / n
                a["score_rate"] = a.pop("score_hits") / n
    for b in bins:
        b["avg_predicted"] = b.pop("p") / b["n"] if b["n"] else None
        b["actual"] = b.pop("hits") / b["n"] if b["n"] else None
    return rnd({"by_league": out, "calibration": bins, "matches": len(scored)})
