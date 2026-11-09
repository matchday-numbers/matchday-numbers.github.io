"""Backtest of the 60/40 recipe (model/recipe.py) on every competition.

Walk-forward by week: at each Monday the ratings are refitted on games played before it, then every
match of that week is estimated. Tuned on 2024-25, tested once on 2025-26. Compared with the plain
league (or European) average and with the previous model's stored results.

  python -m backtest.recipe     -> backtest/results_recipe.json, model/tuned_recipe.json
"""
from __future__ import annotations

import copy
import itertools
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.run import score_stat  # noqa: E402
from model import adjustments as adj  # noqa: E402
from model.core import STATS, has_stat  # noqa: E402
from model.data import load_file  # noqa: E402
from model.europe import EUROPE_CTX, assemble  # noqa: E402
from model.predict import load_tuned  # noqa: E402
from model.ratings import Ratings, league_groups  # noqa: E402
from model.recipe import Recipe  # noqa: E402
from pipeline.referees import join as referee_join, load_rows as load_referee_rows  # noqa: E402
from pipeline.sources import DOMESTIC, FOTMOB_STATS, JOINT_SKIP  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "data", "history")
FD_SEASONS = ["2223", "2324", "2425", "2526"]
EU_SEASONS = ["2324", "2425", "2526"]
TUNE, TEST = "2425", "2526"
COMPS = ["champions-league", "europa-league", "conference-league"]
DATA = None


def data():
    global DATA
    if DATA is None:
        fd = {lg: [m for s in FD_SEASONS for m in load_file(os.path.join(H, f"{lg}_{s}.csv"), lg, s)] for lg in DOMESTIC}
        rows, clubs = [], {}
        for s in EU_SEASONS:
            rows += json.load(open(os.path.join(H, f"europe_{s}.json")))
            for tid, games in json.load(open(os.path.join(H, f"europe_clubs_{s}.json"))).items():
                clubs.setdefault(tid, []).extend(games)
        matches, groups, names = assemble(fd, rows, clubs)
        referees = referee_join(matches, names, load_referee_rows(H), DOMESTIC)
        for m in matches:  # MLS: FotMob, its first stats source, already names the referee
            if m["ctx"] in FOTMOB_STATS and m.get("referee"):
                referees.setdefault((m["date"], m["home"], m["away"]), m["referee"])
        # last game before each match, any competition (club schedules include cups)
        played = defaultdict(set)
        for m in matches:
            played[m["home"]].add(m["date"])
            played[m["away"]].add(m["date"])
        euro_days = defaultdict(set)
        for tid, games in clubs.items():
            for g in games:
                played[tid].add(g["date"][:10])
        for m in matches:
            if m["ctx"] == EUROPE_CTX:
                euro_days[m["home"]].add(m["date"])
                euro_days[m["away"]].add(m["date"])
        played = {t: sorted(v) for t, v in played.items()}
        DATA = {"matches": matches, "groups": groups, "names": names, "referees": referees,
                "played": played, "euro_days": euro_days}
    return DATA


def rest_info(team, d):
    D = data()
    days = D["played"].get(team, [])
    prev = [x for x in days if x < d]
    if not prev:
        return None, False
    last = prev[-1]
    rest = (date.fromisoformat(d) - date.fromisoformat(last)).days
    euro = last in D["euro_days"].get(team, set()) and rest <= 4
    return rest, euro


def stakes_flag(m, tables):
    if m["ctx"] == EUROPE_CTX:
        return "Knockout tie" if m["date"][5:7] in ("02", "03", "04", "05", "06") else None
    t = tables.get(m["ctx"])
    if not t:
        return None
    n_teams = len(t)
    played = sum(v[1] for v in t.values()) / max(n_teams, 1)
    if played < 0.6 * 2 * (n_teams - 1):
        return None
    ranked = sorted(t, key=lambda k: -t[k][0])
    pos = {k: i + 1 for i, k in enumerate(ranked)}
    ph, pa = pos.get(m["home"]), pos.get(m["away"])
    if not ph or not pa:
        return None
    gap = abs(t[m["home"]][0] - t[m["away"]][0])
    if ph <= 6 and pa <= 6 and gap <= 6:
        return "Top-of-table match late in the season"
    if ph > n_teams - 6 and pa > n_teams - 6 and gap <= 6:
        return "Relegation battle late in the season"
    return None


def tables_before(d):
    out = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    season_start = f"{d[:4] if d[5:7] >= '07' else int(d[:4]) - 1}-07-01"
    for m in data()["matches"]:
        if m["ctx"] in DOMESTIC and season_start <= m["date"] < d:
            for t, gf, ga in ((m["home"], m["hg"], m["ag"]), (m["away"], m["ag"], m["hg"])):
                r = out[m["ctx"]][t]
                r[0] += 3 if gf > ga else 1 if gf == ga else 0
                r[1] += 1
    return out


def weeks(season):
    lo = date(2000 + int(season[:2]), 7, 1)
    hi = date(2000 + int(season[2:]), 7, 1)
    d = lo - timedelta(days=lo.weekday())
    while d < hi:
        yield d.isoformat(), (d + timedelta(days=7)).isoformat()
        d += timedelta(days=7)


def rating_args(cfg, joint=False, stat=None):
    """Ratings() arguments. `tau` (how far a team may sit from its league's level) can be set per stat:
    cfg["tau_by_stat"] for league fits, cfg["joint_tau_by_stat"] for the all-competition fit."""
    a = {k: v for k, v in cfg.items() if k in ("half_life", "tau", "sigma", "home_tau", "venue_tau")}
    if joint:
        a["tau"] = (cfg.get("joint_tau_by_stat") or {}).get(stat, cfg.get("joint_tau", 0.35))
    else:
        a["tau"] = (cfg.get("tau_by_stat") or {}).get(stat, cfg.get("tau", 0.3))
    return a


def _fit_week(args):
    d, cfg = args
    D = data()
    start = f"{int(d[:4]) - 3}{d[4:]}"
    window = [m for m in D["matches"] if start <= m["date"] < d]
    lf = {}
    for lg in DOMESTIC:
        lm = [m for m in window if m["ctx"] == lg]
        if not lm:
            continue
        g = league_groups(lm, start)
        lf[lg] = {s: Ratings(**rating_args(cfg, stat=s)).fit(lm, g, s, d) for s in STATS}
    jw = [m for m in window if m["ctx"] not in JOINT_SKIP]
    jf = {s: Ratings(**rating_args(cfg, joint=True, stat=s)).fit(jw, D["groups"], s, d) for s in STATS}
    return d, lf, jf


def fit_season(season, cfg):
    jobs = [(a, cfg) for a, b in weeks(season)
            if any(a <= m["date"] < b and (m["ctx"] in DOMESTIC or m.get("comp")) for m in data()["matches"])]
    with ProcessPoolExecutor() as ex:
        return {d: (lf, jf) for d, lf, jf in ex.map(_fit_week, jobs)}


def eval_matches(season):
    lo, hi = f"20{season[:2]}-07-01", f"20{season[2:]}-07-01"
    return [m for m in data()["matches"] if lo <= m["date"] < hi and (m["ctx"] in DOMESTIC or m.get("comp"))]


def predict_season(season, fits, params, tuning, base_only=False):
    D = data()
    out = []
    week_of = {}
    for a, b in weeks(season):
        week_of.update({(date.fromisoformat(a) + timedelta(days=i)).isoformat(): a for i in range(7)})
    by_week = defaultdict(list)
    for m in eval_matches(season):
        by_week[week_of[m["date"]]].append(m)
    for wk, ms in sorted(by_week.items()):
        if wk not in fits:
            continue
        lf, jf = fits[wk]
        rec = Recipe(params, tuning).attach(D["matches"], wk, lf, jf, D["referees"])
        tables = tables_before(wk)
        for m in ms:
            if base_only:
                lam = {s: rec.fit_for(m["ctx"], s).expect(m["home"], m["away"], m["ctx"]) for s in STATS}
            else:
                info = {"referee": D["referees"].get((m["date"], m["home"], m["away"])),
                        "derby": adj.is_derby(D["names"].get(m["home"], ""), D["names"].get(m["away"], "")),
                        "stakes": stakes_flag(m, tables)}
                for side in ("home", "away"):
                    info[f"{side}_rest_days"], info[f"{side}_europe_midweek"] = rest_info(m[side], m["date"])
                p = rec.predict(m["home"], m["away"], m["ctx"], info, fast=True)
                lam = {s: (p["stats"][s]["home"], p["stats"][s]["away"]) for s in STATS}
            out.append((m, lam))
    return out


def baseline_season(season):
    out = []
    ms_all = data()["matches"]
    cache = {}
    for m in eval_matches(season):
        key = (m["ctx"] if m["ctx"] in DOMESTIC else "europe", m["date"])
        if key not in cache:
            y = f"{int(m['date'][:4]) - 1}{m['date'][4:]}"
            prev = [x for x in ms_all if y <= x["date"] < m["date"] and
                    (x["ctx"] == key[0] if key[0] != "europe" else x.get("comp"))]
            lam = {}
            for s, (hk, ak) in STATS.items():
                v = [x for x in prev if has_stat(x, s)]
                lam[s] = (sum(x[hk] for x in v) / len(v), sum(x[ak] for x in v) / len(v)) if v else (1.4, 1.1)
            cache[key] = lam
        out.append((m, cache[key]))
    return out


def group(pairs_, key):
    g = defaultdict(list)
    for m, lam in pairs_:
        g[key(m)].append((m, lam))
    return g


def comp_of(m):
    return m["ctx"] if m["ctx"] in DOMESTIC else m.get("comp")


def evaluate(pairs_, params, alpha):
    p = copy.deepcopy(params)
    p.nb_alpha = {**p.nb_alpha, **alpha}
    return {s: score_stat(s, pairs_, p) for s in STATS}


def fit_alpha(pairs_, stat):
    hk, ak = STATS[stat]
    num = den = 0.0
    for m, lam in pairs_:
        if has_stat(m, stat):
            mu = sum(lam[stat])
            num += (m[hk] + m[ak] - mu) ** 2 - mu
            den += mu * mu
    return max(num / den, 0.0) if den else 0.0


def measure(pairs_base, flag, stat="cards"):
    """Actual / base-expected over matches where flag(m) is true."""
    hk, ak = STATS[stat]
    act = exp = 0.0
    n = 0
    for m, lam in pairs_base:
        if flag(m) and has_stat(m, stat):
            act += m[hk] + m[ak]
            exp += sum(lam[stat])
            n += 1
    return (act / exp - 1 if exp else 0.0), n


def load_owner():
    """Settings the owner chose on top of the measured ones (kept across re-tuning)."""
    try:
        return json.load(open(os.path.join(ROOT, "model", "tuned_recipe.json"))).get("owner", {})
    except (OSError, ValueError):
        return {}


def main():
    params, _ = load_tuned()
    if os.environ.get("RECIPE_TEST_ONLY"):  # re-test the current settings without re-tuning
        t = json.load(open(os.path.join(ROOT, "model", "tuned_recipe.json")))
        test(t["rating"], t["tuning"], params)
        return
    D = data()
    print(f"matches {len(D['matches'])}, referee-linked {len(D['referees'])}", flush=True)
    # ------------------------------------------------ 1. base ratings (60%)
    best = None
    grid = json.loads(os.environ["RECIPE_BASE_GRID"]) if os.environ.get("RECIPE_BASE_GRID") else \
        [[300.0, 0.04]]  # chosen on 2024-25 from half_life 200/300/600 x venue_tau 0.04/0.08/0.12/0.2
    for hl, vt in grid:
        cfg = {"half_life": hl, "tau": 0.3, "venue_tau": vt, "joint_tau": 0.35}
        fits = fit_season(TUNE, cfg)
        pb = predict_season(TUNE, fits, params, {"form_k": 6.0}, base_only=True)
        res = evaluate(pb, params, {})
        obj = sum(r["objective"] for r in res.values())
        print(f"  base half_life={hl:.0f} venue_tau={vt}: {obj:.4f} (1X2 ll {res['goals']['ll']:.4f})", flush=True)
        if best is None or obj < best[0]:
            best = (obj, cfg, fits, pb)
    _, cfg, fits, pb = best
    print("  chosen base", cfg, flush=True)
    # 1b. how far teams may sit from their league's level, per stat (league fits for league games,
    # the joint fit for European games). One wide setting for every stat overstated team differences
    # in corners, cards and shots (worse than the plain average out of sample).
    taus = [float(x) for x in os.environ.get("RECIPE_TAU_GRID", "0.05,0.08,0.12,0.18,0.3").split(",")]
    scores = {}
    for x in taus:
        c = {**cfg, "tau": x, "joint_tau": x}
        f = fits if x == cfg["tau"] == cfg["joint_tau"] else fit_season(TUNE, c)
        p = predict_season(TUNE, f, params, {"form_k": 6.0}, base_only=True)
        dom = evaluate([q for q in p if q[0]["ctx"] in DOMESTIC], params, {})
        eu = evaluate([q for q in p if q[0].get("comp")], params, {})
        scores[x] = (dom, eu)
        print(f"  tau={x}: league " + " ".join(f"{st[:5]} {dom[st]['objective']:.4f}" for st in STATS)
              + " | europe " + " ".join(f"{st[:5]} {eu[st]['objective']:.4f}" for st in STATS), flush=True)
    cfg = {**cfg,
           "tau_by_stat": {st: min(taus, key=lambda x: scores[x][0][st]["objective"]) for st in STATS},
           "joint_tau_by_stat": {st: min(taus, key=lambda x: scores[x][1][st]["objective"]) for st in STATS}}
    print("  chosen spread", cfg["tau_by_stat"], cfg["joint_tau_by_stat"], flush=True)
    fits = fit_season(TUNE, cfg)
    pb = predict_season(TUNE, fits, params, {"form_k": 6.0}, base_only=True)
    if os.environ.get("RECIPE_BASE_ONLY"):
        return
    # ------------------------------------------------ 2. measured adjustment sizes (on the tuning season)
    tables = {}
    derby_eff, derby_n = measure(pb, lambda m: adj.is_derby(D["names"].get(m["home"], ""), D["names"].get(m["away"], "")))
    stakes_eff, stakes_n = measure(pb, lambda m: bool(stakes_flag(m, tables.setdefault(m["date"][:7], tables_before(m["date"][:7] + "-01")))))
    hk, ak = STATS["goals"]
    act = exp = 0.0
    cn = 0
    for m, lam in pb:
        for side, j in (("home", 0), ("away", 1)):
            rest, euro = rest_info(m[side], m["date"])
            if (rest is not None and rest < 4) or euro:
                act += m[hk] if side == "home" else m[ak]
                exp += lam["goals"][j]
                cn += 1
    cong_eff = act / exp - 1 if exp else 0.0
    print(f"  derby cards {derby_eff:+.3f} (n={derby_n}), stakes cards {stakes_eff:+.3f} (n={stakes_n}), congestion goals {cong_eff:+.3f} (n={cn})", flush=True)
    tuning = {"form_k": 6.0, "h2h_k": 4.0,
              "derby_cards": round(derby_eff, 3) if derby_n >= 40 else 0.0,
              "stakes_cards": round(stakes_eff, 3) if stakes_n >= 40 and abs(stakes_eff) >= 0.03 else 0.0,
              "congestion_goals": round(cong_eff, 3) if cn >= 100 and abs(cong_eff) >= 0.02 else 0.0}
    # ------------------------------------------------ 3. momentum, head-to-head and referee strength
    # Each is a shrinkage constant (bigger = weaker). Stats don't interact, so each stat gets its own
    # strengths; momentum is never switched off (it's part of the recipe), its size is just measured.
    best_by_stat = {}
    for fk, hk2, rk in itertools.product([16.0, 32.0, 64.0, 128.0], [4.0, 16.0], [10.0, 30.0, 60.0]):
        if rk != 30.0 and (fk, hk2) != (16.0, 4.0):
            continue  # referee strength only matters for cards; checked once
        t = {**tuning, "form_k": fk, "h2h_k": hk2, "referee_k": rk}
        pr = predict_season(TUNE, fits, params, t)
        alpha = {st: round(fit_alpha(pr, st), 4) for st in STATS if st != "goals"}
        res = evaluate(pr, params, alpha)
        print(f"  form_k={fk} h2h_k={hk2} referee_k={rk}: " + " ".join(f"{st[:5]} {res[st]['objective']:.4f}" for st in STATS), flush=True)
        for st in STATS:
            if st != "cards" and rk != 30.0:
                continue
            o = res[st]["objective"]
            if st not in best_by_stat or o < best_by_stat[st][0]:
                best_by_stat[st] = (o, fk, hk2, rk, alpha.get(st))
    tuning = {**tuning,
              "form_k": {st: v[1] for st, v in best_by_stat.items()},
              "h2h_k": {st: v[2] for st, v in best_by_stat.items()},
              "referee_k": best_by_stat["cards"][3],
              "nb_alpha": {st: v[4] for st, v in best_by_stat.items() if st != "goals"}}
    print("  chosen", {k: v for k, v in tuning.items() if k != "nb_alpha"}, flush=True)
    test(cfg, tuning, params)


def test(cfg, tuning, params):
    """4. test once on 2025-26, with the owner's settings (tuned_recipe.json "owner", e.g. adj_strength)
    applied on top of the measured ones; the measured-size version is kept for comparison."""
    owner = {k: v for k, v in load_owner().items() if not k.startswith("_")}
    fits = fit_season(TEST, cfg)
    model = predict_season(TEST, fits, params, {**tuning, **owner})
    measured = predict_season(TEST, fits, params, tuning) if owner else model
    base = baseline_season(TEST)
    alpha = tuning["nb_alpha"]
    gx = group(measured, comp_of)
    prev = json.load(open(os.path.join(ROOT, "backtest", "results.json")))["by_league"]
    prev_eu = json.load(open(os.path.join(ROOT, "backtest", "results_europe.json")))["by_comp"]
    gm, gb = group(model, comp_of), group(base, comp_of)
    by_comp = {}
    print("Test 2025-26 (vs average | vs previous model):", flush=True)
    for c in DOMESTIC + COMPS:
        rm, rb, rx = evaluate(gm[c], params, alpha), evaluate(gb[c], params, alpha), evaluate(gx[c], params, alpha)
        pv = prev.get(c) or prev_eu.get(c)
        by_comp[c] = {"matches": len(gm[c]), "brier_1x2": rm["goals"]["brier"], "baseline_brier_1x2": rb["goals"]["brier"],
                      "ll_1x2": rm["goals"]["ll"], "baseline_ll_1x2": rb["goals"]["ll"],
                      "prev_brier_1x2": pv["brier_1x2"] if pv else None, "measured_brier_1x2": rx["goals"]["brier"],
                      "stats": {s: {"objective": rm[s]["objective"], "baseline_objective": rb[s]["objective"],
                                    "prev_objective": pv["stats"][s]["objective"] if pv else None,
                                    "measured_objective": rx[s]["objective"],
                                    "mae": rm[s]["mae"], "baseline_mae": rb[s]["mae"]} for s in STATS}}
        v = by_comp[c]
        print(f"  {c:18s} n={v['matches']:3d} 1X2 brier {v['brier_1x2']:.4f} avg {v['baseline_brier_1x2']:.4f} prev {v['prev_brier_1x2'] or 0:.4f} | "
              + " ".join(f"{s[:4]} {(1 - x['objective'] / x['baseline_objective']) * 100:+.1f}%/{(x['prev_objective'] - x['objective']) / x['prev_objective'] * 100 if x['prev_objective'] else 0:+.1f}%"
                         for s, x in v["stats"].items()), flush=True)
    allm, allb, allx = evaluate(model, params, alpha), evaluate(base, params, alpha), evaluate(measured, params, alpha)
    if owner:
        print("  owner settings", owner, "vs measured sizes: " + " ".join(
            f"{s[:5]} {(allx[s]['objective'] - allm[s]['objective']) / allx[s]['objective'] * 100:+.2f}%" for s in STATS)
            + f" | 1X2 brier {allm['goals']['brier']:.4f} vs {allx['goals']['brier']:.4f}", flush=True)
    from model.core import count_probabilities, goal_probabilities
    bins = [{"lo": i / 10, "hi": (i + 1) / 10, "n": 0, "p": 0.0, "hits": 0} for i in range(10)]
    for m, lam in model:
        for s in STATS:
            if not has_stat(m, s):
                continue
            hk, ak = STATS[s]
            tot = m[hk] + m[ak]
            lh, la = lam[s]
            if s == "goals":
                gp = goal_probabilities(lh, la, params.dc_rho)
                ev = [(gp["home_win"], m[hk] > m[ak]), (gp["draw"], m[hk] == m[ak]), (gp["away_win"], m[hk] < m[ak])]
                ev += [(p_, tot > float(ln)) for ln, p_ in gp["over"].items()]
            else:
                ev = [(p_, tot > float(ln)) for ln, p_ in count_probabilities(s, lh, la, alpha[s])["over"].items()]
            for p_, y in ev:
                b = bins[min(int(p_ * 10), 9)]
                b["n"] += 1
                b["p"] += p_
                b["hits"] += int(y)
    for b in bins:
        b["avg_predicted"] = b.pop("p") / b["n"] if b["n"] else None
        b["actual"] = b.pop("hits") / b["n"] if b["n"] else None
        if b["n"]:
            print(f"    {b['lo']:.0%}-{b['hi']:.0%}: n={b['n']:5d} predicted {b['avg_predicted']:.1%} actual {b['actual']:.1%}", flush=True)
    out = {"season": TEST, "rating": cfg, "tuning": tuning, "owner": owner, "matches": len(model),
           "test": allm, "baseline": allb, "measured": allx, "by_comp": by_comp, "calibration": bins}
    json.dump(out, open(os.path.join(ROOT, "backtest", "results_recipe.json"), "w"), indent=1, default=float)
    json.dump({"rating": cfg, "tuning": tuning, "owner": load_owner()}, open(os.path.join(ROOT, "model", "tuned_recipe.json"), "w"), indent=1)
    print(f"ALL n={len(model)} 1X2 brier {allm['goals']['brier']:.4f} vs avg {allb['goals']['brier']:.4f}", flush=True)


if __name__ == "__main__":
    main()
