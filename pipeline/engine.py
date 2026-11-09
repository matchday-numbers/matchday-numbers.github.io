"""Live side of the 60/40 recipe (model/recipe.py): one engine for every competition."""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from datetime import date, timedelta

from model.core import STATS, Params, count_probabilities, goal_probabilities
from model.data import load_file
from model.europe import EUROPE_CTX, assemble
from model.predict import load_tuned
from model.ratings import Ratings, league_groups
from model.recipe import Recipe
from pipeline import referees as refmod
from pipeline.europe import club_schedules, live_rows
from pipeline.predictions import rnd
from pipeline.sources import DOMESTIC, EUROPE, FOTMOB_STATS, JOINT_SKIP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(ROOT, "data", "history")
TUNED = os.path.join(ROOT, "model", "tuned_recipe.json")


def load_recipe_tuning():
    with open(TUNED) as f:
        return json.load(f)


def rating_args(cfg, joint=False, stat=None):
    """Ratings() arguments. `tau` (how far a team may sit from its league's level) can be set per stat:
    cfg["tau_by_stat"] for league fits, cfg["joint_tau_by_stat"] for the all-competition fit."""
    a = {k: v for k, v in cfg.items() if k in ("half_life", "tau", "sigma", "home_tau", "venue_tau")}
    if joint:
        a["tau"] = (cfg.get("joint_tau_by_stat") or {}).get(stat, cfg.get("joint_tau", 0.35))
    else:
        a["tau"] = (cfg.get("tau_by_stat") or {}).get(stat, cfg.get("tau", 0.3))
    return a


def fit(allm, groups, asof):
    """Per-league fits (league games only) and one joint fit over all competitions, as of `asof`."""
    cfg = load_recipe_tuning()["rating"]
    start = f"{int(asof[:4]) - 3}{asof[4:]}"
    window = [m for m in allm if start <= m["date"] < asof]
    lf = {}
    for lg in DOMESTIC:
        lm = [m for m in window if m["ctx"] == lg]
        if lm:
            g = league_groups(lm, start)
            lf[lg] = {s: Ratings(**rating_args(cfg, stat=s)).fit(lm, g, s, asof) for s in STATS}
    jw = [m for m in window if m["ctx"] not in JOINT_SKIP]  # leagues with no clubs in Europe add nothing there
    jf = {s: Ratings(**rating_args(cfg, joint=True, stat=s)).fit(jw, groups, s, asof) for s in STATS}
    return lf, jf


def build(season, now, fd, matches, events, team_map, sdir, log, jload, jsave, live_ref_rows):
    t = load_recipe_tuning()
    params, _ = load_tuned()
    y = 2000 + int(season[:2])
    hist_fd = {}
    for lg in DOMESTIC:
        files = sorted(glob.glob(os.path.join(HISTORY, f"{lg}_*.csv")))[-3:]
        hist = [m for f in files for m in load_file(f, lg, os.path.basename(f)[-8:-4])]
        last = max((m["date"] for m in hist), default="")
        # this season: the cross-checked records (stats the two sources disagree on are already removed);
        # MLS's window reaches back into games the history files already hold, so those are skipped
        hist_fd[lg] = hist + [m for m in matches.get(lg, []) if m["date"] > last]
    rows, clubs = [], {}
    for f in sorted(glob.glob(os.path.join(HISTORY, "europe_[0-9]*.json")))[-3:]:
        rows += json.load(open(f))
    for f in sorted(glob.glob(os.path.join(HISTORY, "europe_clubs_*.json")))[-3:]:
        for tid, games in json.load(open(f)).items():
            clubs.setdefault(tid, []).extend(games)
    for lg in EUROPE:
        rows += live_rows(lg, matches[lg], events[lg])
    ids = sorted({e[side]["espn_id"] for lg in EUROPE for e in events[lg].values() for side in ("home", "away") if e[side].get("espn_id")})
    for tid, games in club_schedules(os.path.join(sdir, "europe_clubs.json"), ids, y, now, log, jload, jsave).items():
        clubs.setdefault(tid, []).extend(games)
    extra = {lg: {n: tm["espn_id"] for n, tm in (team_map.get(lg) or {}).items()} for lg in DOMESTIC}
    allm, groups, names = assemble(hist_fd, rows, clubs, extra)
    refs = refmod.join(allm, names, refmod.load_rows(HISTORY) + list(live_ref_rows), DOMESTIC)
    for m in allm:  # MLS: FotMob, its first stats source, already names the referee
        if m["ctx"] in FOTMOB_STATS and m.get("referee"):
            refs.setdefault((m["date"], m["home"], m["away"]), m["referee"])
    asof = (now + timedelta(days=1)).date().isoformat()
    lf, jf = fit(allm, groups, asof)
    owner = {k: v for k, v in t.get("owner", {}).items() if not k.startswith("_")}  # owner's choices on top
    rec = Recipe(Params(**{**params.__dict__}), {**t["tuning"], **owner}).attach(allm, asof, lf, jf, refs)
    rec.all_matches, rec.groups, rec.names = allm, groups, names
    log["model"] = {"matches": len([m for m in allm if m["date"] >= f"{int(asof[:4]) - 3}{asof[4:]}"]),
                    "teams": len(jf["goals"].att), "referees_linked": len(refs)}
    return rec


def baseline(rec, ctx_key):
    """Plain average for the competition (what you'd predict knowing nothing about the teams)."""
    out = {}
    for stat in STATS:
        mh, ma = rec.fit_for(ctx_key, stat).venue(ctx_key)
        if stat == "goals":
            g = goal_probabilities(mh, ma, rec.params.dc_rho)
            out[stat] = {"total": mh + ma, "home_win": g["home_win"], "draw": g["draw"], "away_win": g["away_win"],
                         "over": g["over"], "btts": g["btts"]}
        else:
            alpha = rec.t.get("nb_alpha", {}).get(stat, rec.params.nb_alpha.get(stat, 0.03))
            out[stat] = {"total": mh + ma, **count_probabilities(stat, mh, ma, alpha)}
    return out


def missing_info(players, squad, find_player):
    """Adds each missing player's share of team goal involvement and whether he's a regular defender."""
    total = sum(p["goals"] + 0.5 * p["assists"] for p in squad.values())
    games = max((p.get("apps", 0) for p in squad.values()), default=0)
    out = []
    for x in players:
        p = find_player(x["name"], squad) if squad else None
        share = (p["goals"] + 0.5 * p["assists"]) / total if p and total else 0.0
        reg = bool(p and (p.get("pos") in ("G", "D")) and games and p.get("starts", 0) >= 0.6 * games)
        out.append({**x, "share": round(share, 3), "regular_defender": reg, "position": (p or {}).get("pos") or x.get("position")})
    return out


def stakes_now(lg, table_rows, home, away, kickoff):
    """'High stakes' label (cards adjustment): late-season top or bottom clashes; European knockouts."""
    if lg in EUROPE:
        return "Knockout tie" if kickoff[5:7] in ("02", "03", "04", "05", "06") else None
    n = len(table_rows)
    if not n:
        return None
    played = sum(r["p"] for r in table_rows) / n
    if played < 0.6 * 2 * (n - 1):
        return None
    pos = {r["team"]: r for r in table_rows}
    h, a = pos.get(home), pos.get(away)
    if not h or not a or abs(h["pts"] - a["pts"]) > 6:
        return None
    if h["pos"] <= 6 and a["pos"] <= 6:
        return "Top-of-table match late in the season"
    if h["pos"] > n - 6 and a["pos"] > n - 6:
        return "Relegation battle late in the season"
    return None


def league_table(ms):
    t = defaultdict(lambda: {"p": 0, "pts": 0, "gd": 0})
    for m in ms:
        for side, gf, ga in (("home", m["hg"], m["ag"]), ("away", m["ag"], m["hg"])):
            r = t[m[side]]
            r["p"] += 1
            r["pts"] += 3 if gf > ga else 1 if gf == ga else 0
            r["gd"] += gf - ga
    rows = sorted(({"team": k, **v} for k, v in t.items()), key=lambda r: (-r["pts"], -r["gd"]))
    for i, r in enumerate(rows, 1):
        r["pos"] = i
    return rows


def make(rec, league, fixture, home_file_key, away_file_key, info, labels, made_at, version):
    ctx_key = league if league in DOMESTIC else EUROPE_CTX
    hk, ak = fixture["home"]["espn_id"], fixture["away"]["espn_id"]
    p = rec.predict(hk, ak, ctx_key, info, labels)
    p["league"] = league
    return rnd({
        "id": fixture["espn_id"], "league": league, "kickoff": fixture["kickoff"],
        "home": home_file_key, "away": away_file_key, "made_at": made_at, "model_version": version, "model": "recipe",
        "prediction": p, "baseline": baseline(rec, ctx_key),
        "missing": {"home": info.get("home_missing") or [], "away": info.get("away_missing") or []},
        "doubtful": {"home": info.get("home_doubtful") or [], "away": info.get("away_doubtful") or []},
        "team_news": bool(info.get("injuries_known")), "referee": info.get("referee"),
    })


def retro(rec_factory, done, existing):
    """'Model check' for finished matches that have no frozen estimate: the recipe run as of the Monday
    before each match, from games played before it. Returns {match id: compact estimate}."""
    out = dict(existing)
    todo = [x for x in done if x["id"] not in out]
    by_week = defaultdict(list)
    for x in todo:
        d = date.fromisoformat(x["date"])
        by_week[(d - timedelta(days=d.weekday())).isoformat()].append(x)
    for wk, xs in sorted(by_week.items()):
        rec = rec_factory(wk)
        for x in xs:
            try:
                p = rec.predict(x["home_key"], x["away_key"], x["ctx"], {}, fast=True)
            except Exception:  # noqa: BLE001
                continue
            out[x["id"]] = rnd({"asof": wk, "stats": {s: {k: v[k] for k in ("home", "away", "total", "range", "over") if k in v} for s, v in p["stats"].items()},
                                "goals": {k: p["stats"]["goals"][k] for k in ("home_win", "draw", "away_win", "btts", "likely_scores")}})
    return out
