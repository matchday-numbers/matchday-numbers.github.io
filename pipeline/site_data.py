"""Writes the JSON the website reads (site/data/...)."""
from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
from datetime import timedelta

from pipeline.predictions import aggregate, rnd
from pipeline.sources import DOMESTIC, EUROPE, LEAGUES, PREDICTED

STATS = [("goals", "hg", "ag"), ("corners", "hc", "ac"), ("cards", "hcards", "acards"),
         ("shots", "hs", "as"), ("shots_on_target", "hst", "ast")]


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "team"


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(rnd(obj), f, ensure_ascii=False, separators=(",", ":"))


def write(root, season, now, matches, events, summaries, fd, team_map, espn_teams, squad, pdir, scored, log, reports, retro=None):
    retro = retro or {}
    out = os.path.join(root, "site", "data")
    for sub in ("team", "match"):
        for f in glob.glob(os.path.join(out, sub, "*.json")):
            os.remove(f)

    # ---------------------------------------------------------------- team identities
    ident = {}       # (league, key) -> {slug, name, logo, espn_id}
    by_espn = {}     # espn_id -> ident
    used = {}

    def make_ident(espn_id, fallback_name):
        if espn_id and espn_id in by_espn:
            return by_espn[espn_id]
        t = espn_teams.get(espn_id, {}) if espn_id else {}
        name = t.get("name") or fallback_name
        slug = slugify(name)
        if slug in used and used[slug] != espn_id:
            slug = f"{slug}-{espn_id or 'x'}"
        used[slug] = espn_id
        i = {"slug": slug, "name": name, "short": t.get("short") or name, "logo": t.get("logo"), "espn_id": espn_id,
             "color": t.get("color"), "alt_color": t.get("alt_color"), "abbr": t.get("abbr")}
        if espn_id:
            by_espn[espn_id] = i
        return i

    home_league = {}
    for lg in DOMESTIC:
        names = {m["home"] for m in matches[lg]} | {m["away"] for m in matches[lg]}
        for e in events[lg].values():
            for side in ("home", "away"):
                fdn = next((n for n, t in team_map[lg].items() if t["espn_id"] == e[side]["espn_id"]), None)
                if fdn:
                    names.add(fdn)
        for n in names:
            eid = (team_map[lg].get(n) or {}).get("espn_id")
            ident[(lg, n)] = make_ident(eid, n)
            home_league[ident[(lg, n)]["slug"]] = lg
    for lg in EUROPE:
        for e in events[lg].values():
            for side in ("home", "away"):
                eid = e[side]["espn_id"]
                ident[(lg, eid)] = make_ident(eid, e[side]["name"])

    def tid(lg, key):
        i = ident.get((lg, key)) or make_ident(None, str(key))
        return {k: i.get(k) for k in ("slug", "name", "short", "logo", "color", "alt_color", "abbr")}

    # ---------------------------------------------------------------- per-team rows
    rows = {}  # slug -> list of team-perspective match rows
    for lg, ms in matches.items():
        for m in ms:
            for side, opp in (("home", "away"), ("away", "home")):
                me, them = tid(lg, m[side]), tid(lg, m[opp])
                h = side == "home"
                r = {"id": m.get("espn_id"), "date": m["date"], "kickoff": m.get("kickoff"), "comp": lg,
                     "opp": them, "venue": "H" if h else "A"}
                for stat, hk, ak in STATS:
                    f, a = (m.get(hk), m.get(ak)) if h else (m.get(ak), m.get(hk))
                    r[stat] = [f, a]
                gf, ga = r["goals"]
                r["result"] = "W" if gf > ga else "D" if gf == ga else "L"
                rows.setdefault(me["slug"], []).append(r)
    for r in rows.values():
        r.sort(key=lambda x: (x["date"], x.get("kickoff") or ""))

    def averages(rs):
        out = {}
        for stat, _, _ in STATS:
            v = {}
            for key, sel in (("overall", rs), ("home", [x for x in rs if x["venue"] == "H"]),
                             ("away", [x for x in rs if x["venue"] == "A"])):
                ok = [x[stat] for x in sel if x[stat][0] is not None]
                n = len(ok)
                v[key] = {"for": sum(x[0] for x in ok) / n if n else None,
                          "against": sum(x[1] for x in ok) / n if n else None, "n": n}
            out[stat] = v
        rec = {}
        for key, sel in (("overall", rs), ("home", [x for x in rs if x["venue"] == "H"]),
                         ("away", [x for x in rs if x["venue"] == "A"])):
            n = len(sel)
            rec[key] = {"p": n, "w": sum(x["result"] == "W" for x in sel), "d": sum(x["result"] == "D" for x in sel),
                        "l": sum(x["result"] == "L" for x in sel),
                        "clean_sheets": sum(x["goals"][1] == 0 for x in sel),
                        "btts": sum(x["goals"][0] > 0 and x["goals"][1] > 0 for x in sel),
                        "over25": sum(x["goals"][0] + x["goals"][1] > 2.5 for x in sel)}
        return out, rec

    def form(rs, n):
        sel = rs[-n:]
        if not sel:
            return None
        pts = sum(3 if x["result"] == "W" else 1 if x["result"] == "D" else 0 for x in sel)
        avg, _ = averages(sel)
        return {"results": "".join(x["result"] for x in sel), "ppg": pts / len(sel), "n": len(sel),
                "averages": {k: v["overall"] for k, v in avg.items()}}

    def table(lg):
        t = {}
        ms = matches[lg]
        if lg == "mls":  # one combined table (the Supporters' Shield standings) of the latest season, no playoffs
            ev = events.get(lg, {})
            regs = [m for m in ms if (ev.get(m.get("espn_id")) or {}).get("season_slug") == "regular-season"]
            if regs:
                latest = max((ev[m["espn_id"]].get("season_year") or 0) for m in regs)
                ms = [m for m in regs if (ev[m["espn_id"]].get("season_year") or 0) == latest]
        for m in ms:
            if lg in EUROPE and m["date"] >= f"20{season[2:]}-01-25":
                continue  # knockout rounds are not part of the league phase table
            for side, gf, ga in (("home", m["hg"], m["ag"]), ("away", m["ag"], m["hg"])):
                me = tid(lg, m[side])
                r = t.setdefault(me["slug"], {"team": me, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0})
                r["p"] += 1
                r["gf"] += gf
                r["ga"] += ga
                if gf > ga:
                    r["w"] += 1
                    r["pts"] += 3
                elif gf == ga:
                    r["d"] += 1
                    r["pts"] += 1
                else:
                    r["l"] += 1
        out = sorted(t.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"], r["team"]["name"]))
        for i, r in enumerate(out, 1):
            r["pos"] = i
            r["gd"] = r["gf"] - r["ga"]
            r["form"] = "".join(x["result"] for x in rows.get(r["team"]["slug"], []) if x["comp"] == lg)[-5:]
        return out

    # ---------------------------------------------------------------- predictions on disk
    preds = {}
    for path in glob.glob(os.path.join(pdir, "*", "*.json")):
        with open(path) as f:
            p = json.load(f)
        preds[p["id"]] = p

    def pred_summary(p):
        if not p:
            return None
        s = p["prediction"]["stats"]
        return {"home_win": s["goals"]["home_win"], "draw": s["goals"]["draw"], "away_win": s["goals"]["away_win"],
                "home_goals": s["goals"]["home"], "away_goals": s["goals"]["away"],
                "goals": s["goals"]["total"], "corners": s["corners"]["total"], "cards": s["cards"]["total"],
                "team_news": p["prediction"].get("basis", {}).get("team_news", False), "made_at": p["made_at"]}

    def league_scorers(lg):
        out = []
        for key, players in squad.get(lg, {}).items():
            for p in players.values():
                if p["goals"] or p["assists"]:
                    out.append({"name": p["name"], "team": tid(lg, key), "goals": p["goals"], "assists": p["assists"],
                                "minutes": p["minutes"]})
        out.sort(key=lambda p: (-p["goals"], -p["assists"], p["minutes"]))
        return out[:10]

    # ---------------------------------------------------------------- league files
    upcoming_all = []
    for lg in LEAGUES:
        evs = sorted(events[lg].values(), key=lambda e: e["kickoff"])
        key_of = (lambda e, side, lg=lg: next((n for n, t in team_map[lg].items() if t["espn_id"] == e[side]["espn_id"]), None)) \
            if lg in DOMESTIC else (lambda e, side: e[side]["espn_id"])
        upcoming = []
        for e in evs:
            if e.get("status") == "pre" and e["kickoff"] >= now.isoformat()[:16] and len(upcoming) < 150:
                hk, ak = key_of(e, "home"), key_of(e, "away")
                if hk is None or ak is None:
                    continue
                u = {"id": e["espn_id"], "kickoff": e["kickoff"], "comp": lg, "home": tid(lg, hk), "away": tid(lg, ak),
                     "venue": e.get("venue"), "round": e.get("round"), "prediction": pred_summary(preds.get(e["espn_id"]))}
                upcoming.append(u)
                write_match_upcoming(out, u, preds.get(e["espn_id"]), lg)
        upcoming_all += upcoming
        recent = []
        for m in sorted(matches[lg], key=lambda m: (m["date"], m.get("kickoff") or ""), reverse=True)[:40]:
            recent.append({"id": m.get("espn_id"), "date": m["date"], "kickoff": m.get("kickoff"), "comp": lg,
                           "home": tid(lg, m["home"]), "away": tid(lg, m["away"]), "score": [m["hg"], m["ag"]],
                           "verified": all(v == "verified" for v in m.get("checks", {}).values()),
                           "has_prediction": m.get("espn_id") in preds})
        rep = reports.get(lg, {})
        dump(os.path.join(out, f"league-{lg}.json"), {
            "key": lg, "name": LEAGUES[lg]["name"], "season": season, "table": table(lg),
            "upcoming": upcoming, "recent": recent, "matches_played": len(matches[lg]),
            "cross_check": {k: rep.get(k) for k in ("verified", "single", "conflict")} if rep else None,
            "predictions_available": lg in PREDICTED,
            "scorers": league_scorers(lg),
        })

    # ---------------------------------------------------------------- home page bundle (one small file)
    leaders, scorers_all = [], []
    for lg in LEAGUES:
        tb = table(lg)
        leaders.append({"key": lg, "name": LEAGUES[lg]["name"], "kind": LEAGUES[lg]["kind"],
                        "played": len(matches[lg]), "top": tb[:4]})
        if lg in DOMESTIC:
            scorers_all += [{**p, "comp": lg} for p in league_scorers(lg)]
    scorers_all.sort(key=lambda p: (-p["goals"], -p["assists"], p["minutes"]))
    week = [u for u in upcoming_all if u["kickoff"] <= (now + timedelta(days=7)).isoformat()[:16]]
    pos = {(lg["key"], r["team"]["slug"]): r["pos"] for lg in leaders for r in table(lg["key"])}
    for u in week:
        u["rank"] = [pos.get((u["comp"], u["home"]["slug"])), pos.get((u["comp"], u["away"]["slug"]))]
    dump(os.path.join(out, "home.json"), {"week": sorted(week, key=lambda u: u["kickoff"]), "leaders": leaders,
                                          "scorers": scorers_all[:8]})

    # ---------------------------------------------------------------- search index
    idx = []
    for lg, ms in matches.items():
        for m in ms:
            if m.get("espn_id"):
                idx.append({"id": m["espn_id"], "k": m.get("kickoff") or m["date"], "c": lg,
                            "h": tid(lg, m["home"])["slug"], "a": tid(lg, m["away"])["slug"], "s": [m["hg"], m["ag"]]})
    for u in upcoming_all:
        p = u.get("prediction")
        idx.append({"id": u["id"], "k": u["kickoff"], "c": u["comp"], "h": u["home"]["slug"], "a": u["away"]["slug"],
                    "p": [p["home_win"], p["draw"], p["away_win"]] if p else None})
    idx.sort(key=lambda x: x["k"])
    dump(os.path.join(out, "search.json"), idx)

    # ---------------------------------------------------------------- match files
    for lg, ms in matches.items():
        summ = summaries.get(lg, {})
        for m in ms:
            if not m.get("espn_id"):
                continue
            s = summ.get(m["espn_id"]) or {}
            st = {}
            for stat, hk, ak in STATS:
                st[stat] = [m.get(hk), m.get(ak)]
            st["yellow"] = [m.get("hy"), m.get("ay")]
            st["red"] = [m.get("hr"), m.get("ar")]
            st["fouls"] = [(s.get("teams", {}).get("home") or {}).get("fouls"), (s.get("teams", {}).get("away") or {}).get("fouls")]
            st["possession"] = [(s.get("teams", {}).get("home") or {}).get("possession"),
                                (s.get("teams", {}).get("away") or {}).get("possession")]
            if m.get("hxg") is not None:
                st["xg"] = [m.get("hxg"), m.get("axg")]
            p = preds.get(m["espn_id"])
            dump(os.path.join(out, "match", f"{m['espn_id']}.json"), {
                "id": m["espn_id"], "comp": lg, "date": m["date"], "kickoff": m.get("kickoff"), "status": "finished",
                "round": m.get("round"), "venue": m.get("venue"), "referee": m.get("referee"),
                "home": tid(lg, m["home"]), "away": tid(lg, m["away"]), "score": [m["hg"], m["ag"]],
                "stats": st, "checks": m.get("checks"), "conflict_values": m.get("conflict_values"),
                "sources": m.get("sources"), "lineups": s.get("lineups"), "goals": s.get("goals"), "cards": s.get("cards"),
                "prediction": p, "retro": None if p else retro.get(m["espn_id"]),
            })

    # ---------------------------------------------------------------- team files
    teams_index = []
    for slug, rs in rows.items():
        i = next(v for v in ident.values() if v["slug"] == slug)
        dom = home_league.get(slug)
        if dom:
            comp = dom
        else:  # club from a league we don't cover: use its busiest European competition
            counts = {}
            for r in rs:
                counts[r["comp"]] = counts.get(r["comp"], 0) + 1
            comp = max(counts, key=counts.get)
        lrows = [r for r in rs if r["comp"] == comp]
        avg, rec = averages(lrows)
        key = next((k for (lg, k), v in ident.items() if v["slug"] == slug and lg == comp), None)
        sq = squad.get(comp, {}).get(key, {})
        team_goals = sum(r["goals"][0] for r in lrows) or 1
        scorers = sorted(sq.values(), key=lambda p: (-(p["goals"] + p["assists"]), -p["goals"], -p["minutes"]))
        scorers = [{"name": p["name"], "pos": p["pos"], "goals": p["goals"], "assists": p["assists"], "apps": p["apps"],
                    "starts": p["starts"], "minutes": p["minutes"], "yellow": p["yellow"], "red": p["red"],
                    "share_goals": p["goals"] / team_goals, "share_involvement": (p["goals"] + p["assists"]) / team_goals}
                   for p in scorers if p["goals"] + p["assists"] > 0][:12]
        ups = [u for u in upcoming_all if slug in (u["home"]["slug"], u["away"]["slug"])][:6]
        teams_index.append({"slug": slug, "name": i["name"], "logo": i["logo"], "league": comp,
                            "color": i.get("color"), "domestic": bool(dom)})
        dump(os.path.join(out, "team", f"{slug}.json"), {
            "slug": slug, "name": i["name"], "logo": i["logo"], "color": i.get("color"), "alt_color": i.get("alt_color"),
            "league": comp, "domestic": bool(dom), "season": season,
            "averages": avg, "record": rec, "form": {"last5": form(lrows, 5), "last10": form(lrows, 10)},
            "log": rs, "scorers": scorers, "upcoming": ups,
            "europe": [r for r in rs if r["comp"] in EUROPE] if dom else [],
        })
    dump(os.path.join(out, "teams.json"), sorted(teams_index, key=lambda t: t["name"]))

    # ---------------------------------------------------------------- accuracy
    bt = {}
    bpath = os.path.join(root, "backtest", "results.json")
    if os.path.exists(bpath):
        with open(bpath) as f:
            b = json.load(f)
        bl = b.get("by_league", {})
        bt = {"season": "2025-26", "leagues": [LEAGUES[k]["name"] for k in bl] or ["Premier League", "La Liga"],
              "matches": b.get("matches", 760),
              "by_league": {k: {"matches": v["matches"], "brier_1x2": v["brier_1x2"], "baseline_brier_1x2": v["baseline_brier_1x2"],
                                "gain_x1000": {st: (x["baseline_objective"] - x["objective"]) * 1000 for st, x in v["stats"].items()},
                                "mix_vs_pure_x1000": {st: (x["pure_objective"] - x["objective"]) * 1000 for st, x in v["stats"].items()},
                                "gain_pct": {st: (1 - x["objective"] / x["baseline_objective"]) * 100 for st, x in v["stats"].items()}}
                            for k, v in bl.items()},
              "test": {k: {kk: v[kk] for kk in ("mae", "brier", "ll", "lines") if kk in v} for k, v in b["test"].items()},
              "baseline": {k: {kk: v[kk] for kk in ("mae", "brier", "ll", "lines") if kk in v} for k, v in b["baseline"].items()},
              # log loss x1000 so small differences survive rounding
              "objective_x1000": {k: v["objective"] * 1000 for k, v in b["test"].items()},
              "baseline_objective_x1000": {k: v["objective"] * 1000 for k, v in b["baseline"].items()},
              "pure_objective_x1000": {k: v["objective"] * 1000 for k, v in b.get("pure_stats", {}).items()},
              "calibration": b["calibration"], "tuning": b["tuning"], "adjustment_tests": b["adjustment_tests"]}
    epath = os.path.join(root, "backtest", "results_europe.json")
    if bt and os.path.exists(epath):
        with open(epath) as f:
            e = json.load(f)
        for k, v in e.get("by_comp", {}).items():
            if k in PREDICTED:
                bt["by_league"][k] = {"matches": v["matches"], "brier_1x2": v["brier_1x2"], "baseline_brier_1x2": v["baseline_brier_1x2"],
                                      "gain_x1000": {st: (x["baseline_objective"] - x["objective"]) * 1000 for st, x in v["stats"].items()},
                                      "mix_vs_pure_x1000": {st: (x["pure_objective"] - x["objective"]) * 1000 for st, x in v["stats"].items()},
                                      "gain_pct": {st: (1 - x["objective"] / x["baseline_objective"]) * 100 for st, x in v["stats"].items()}}
        if any(k in PREDICTED for k in EUROPE):
            bt["europe"] = {"matches": e["matches"], "brier": e["test"]["goals"]["brier"], "baseline_brier": e["baseline"]["goals"]["brier"]}
    rpath = os.path.join(root, "backtest", "results_recipe.json")
    if os.path.exists(rpath):  # the current method (60/40 recipe) replaces the earlier test results
        with open(rpath) as f:
            r = json.load(f)
        bc = {k: v for k, v in r["by_comp"].items() if k in PREDICTED}
        bt = {"season": "2025-26", "method": "recipe", "leagues": [LEAGUES[k]["name"] for k in bc], "matches": r["matches"],
              "by_league": {k: {"matches": v["matches"], "brier_1x2": v["brier_1x2"], "baseline_brier_1x2": v["baseline_brier_1x2"],
                                "prev_brier_1x2": v.get("prev_brier_1x2"),
                                "gain_pct": {st: (1 - x["objective"] / x["baseline_objective"]) * 100 for st, x in v["stats"].items()},
                                "vs_prev_pct": {st: ((x["prev_objective"] - x["objective"]) / x["prev_objective"] * 100) if x.get("prev_objective") else None
                                                for st, x in v["stats"].items()}}
                            for k, v in bc.items()},
              "test": {k: {kk: v[kk] for kk in ("mae", "brier", "ll", "lines") if kk in v} for k, v in r["test"].items()},
              "baseline": {k: {kk: v[kk] for kk in ("mae", "brier", "ll", "lines") if kk in v} for k, v in r["baseline"].items()},
              "objective_x1000": {k: v["objective"] * 1000 for k, v in r["test"].items()},
              "baseline_objective_x1000": {k: v["objective"] * 1000 for k, v in r["baseline"].items()},
              "calibration": r.get("calibration", []), "tuning": r["tuning"],
              "owner": {k: v for k, v in (r.get("owner") or {}).items() if not k.startswith("_")},
              "measured_objective_x1000": {k: v["objective"] * 1000 for k, v in (r.get("measured") or {}).items()},
              "measured_brier": (r.get("measured") or {}).get("goals", {}).get("brier")}
    recent = []
    for p in sorted(scored, key=lambda p: p["kickoff"], reverse=True)[:60]:
        r = p["result"]
        lg = p["league"]
        g = r.get("goals", {})
        recent.append({"id": p["id"], "kickoff": p["kickoff"], "comp": lg, "home": tid(lg, p["home"]), "away": tid(lg, p["away"]),
                       "score": g.get("actual"), "p_outcome": g.get("p_outcome"), "pick_correct": g.get("pick_correct"),
                       "goals": [p["prediction"]["stats"]["goals"]["total"], g.get("actual_total")],
                       "corners": [p["prediction"]["stats"]["corners"]["total"], r.get("corners", {}).get("actual_total")],
                       "cards": [p["prediction"]["stats"]["cards"]["total"], r.get("cards", {}).get("actual_total")]})
    dump(os.path.join(out, "accuracy.json"), {"live": aggregate(scored), "recent": recent, "backtest": bt,
                                              "updated_at": now.isoformat()})

    # ---------------------------------------------------------------- meta
    last_fd = {lg: max((m["date"] for m in fd[lg]), default=None) for lg in DOMESTIC}
    dump(os.path.join(out, "meta.json"), {
        "updated_at": now.isoformat(), "season": season, "season_label": f"20{season[:2]}-{season[2:]}",
        "leagues": [{"key": k, "name": v["name"], "short": v["short"], "kind": v["kind"], "country": v["country"]}
                    for k, v in LEAGUES.items()],
        "sources": {"football_data_last_match": last_fd,
                    "espn_calls": log.get("calls", {}).get("espn"), "errors": len(log.get("errors", []))},
        "cross_check": {lg: reports[lg] and {k: reports[lg][k] for k in ("verified", "single", "conflict")} for lg in DOMESTIC},
        "upcoming_count": len(upcoming_all),
    })


def write_match_upcoming(out, u, pred, lg):
    note = None
    if lg in EUROPE:
        note = (f"No estimate: {LEAGUES[lg]['name']} teams come from different leagues, and their numbers "
                "can't be compared reliably yet. Full stats appear here after the match.")
    elif lg not in PREDICTED:
        note = "Estimates for this league are switched off: they didn't pass the test on last season."
    elif not pred:
        note = "The estimate appears up to a month before kick-off."
    dump(os.path.join(out, "match", f"{u['id']}.json"), {
        "id": u["id"], "comp": lg, "kickoff": u["kickoff"], "status": "upcoming", "round": u.get("round"),
        "venue": u.get("venue"), "home": u["home"], "away": u["away"], "prediction": pred, "note": note})
