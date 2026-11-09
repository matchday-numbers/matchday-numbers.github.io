"""Estimates for European competition matches (Champions, Europa, Conference League).

Teams come from different leagues, so the statistical base (60%) is a joint rating model fitted on
every match we have: the seven covered leagues (football-data.co.uk, with stats), the domestic and
qualifying games of every club that played in Europe (ESPN schedules, results only), and the European
matches themselves (ESPN, with stats). For each stat:

    log E[home value] = mu[ctx] + H[ctx] + att[home] - dfn[away]
    log E[away value] = mu[ctx]          + att[away] - dfn[home]

ctx is the competition (each league has its own level; all European games share one). Team ratings
are shrunk toward their league's level, and league levels toward zero; European games are what put
leagues on one scale. Older games count less (half-life).

The other 40% mirrors the league model: form (last 5 games, any competition, against what the ratings
expected), strength gap (difference in overall goal rating, effects measured on past European games)
and head-to-head meetings.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date

import numpy as np
from scipy.optimize import minimize

from .core import LINES, STATS, count_probabilities, goal_probabilities, has_stat

EUROPE_CTX = "europe"
VIEW_WEIGHTS = {"form": 0.40, "gap": 0.35, "h2h": 0.25}
COVERED_SLUGS = {"eng.1": "premier-league", "esp.1": "la-liga", "ita.1": "serie-a", "ger.1": "bundesliga",
                 "fra.1": "ligue-1", "ned.1": "eredivisie", "por.1": "primeira-liga", "tur.1": "super-lig",
                 "esp.2": "segunda-division", "usa.1": "mls"}
TOP_FLIGHT = re.compile(r"^[a-z]{3}\.1$")


def _d(s):
    return date.fromisoformat(s[:10])


# ---------------------------------------------------------------- assembling the data
def map_covered_teams(fd_matches, sched_games):
    """football-data.co.uk names -> ESPN ids, by matching games on date and score (votes)."""
    by_day = defaultdict(list)
    for g in sched_games:
        by_day[g["date"][:10]].append(g)
    votes = defaultdict(lambda: defaultdict(float))
    for m in fd_matches:
        d = _d(m["date"])
        cands = []
        for k in (0, 1, -1):
            day = date.fromordinal(d.toordinal() + k).isoformat()
            cands += [g for g in by_day.get(day, []) if g["hg"] == m["hg"] and g["ag"] == m["ag"]]
        for g in cands:
            votes[m["home"]][g["home"]["id"]] += 1 / len(cands)
            votes[m["away"]][g["away"]["id"]] += 1 / len(cands)
    out = {}
    for name, v in votes.items():
        ranked = sorted(v.items(), key=lambda kv: -kv[1])
        top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if top[1] >= 1.5 and top[1] >= 2 * second:
            out[name] = top[0]
    return out


def assemble(fd_by_league, europe_rows, club_schedules, extra_map=None):
    """Builds one list of matches with team keys on a common scale.

    fd_by_league: {league: [model match dicts]} (covered leagues, any seasons)
    europe_rows: European matches (tools/collect_europe.py format, or live records converted to it)
    club_schedules: {espn_team_id: [schedule games]} (results only)
    extra_map: {league: {fd_name: espn_id}} known mappings (e.g. the live season's teams.json)
    Returns (matches, groups, names) where groups maps team key -> league group.
    """
    sched_games = {}
    for games in club_schedules.values():
        for g in games:
            sched_games[g["id"]] = g
    sched_games = list(sched_games.values())
    matches, groups, names = [], {}, {}

    # covered leagues: football-data.co.uk records, mapped to ESPN ids where possible
    slug_of = {v: k for k, v in COVERED_SLUGS.items()}
    for lg, ms in fd_by_league.items():
        games = [g for g in sched_games if g.get("league") == slug_of.get(lg)]
        mp = {**map_covered_teams(ms, games), **((extra_map or {}).get(lg) or {})}
        for m in ms:
            h = mp.get(m["home"]) or f"{lg}:{m['home']}"
            a = mp.get(m["away"]) or f"{lg}:{m['away']}"
            groups.setdefault(h, lg)
            groups.setdefault(a, lg)
            names.setdefault(h, m["home"])
            names.setdefault(a, m["away"])
            r = {k: m.get(k) for k in ("hg", "ag", "hc", "ac", "hcards", "acards", "hs", "as", "hst", "ast")}
            matches.append({"date": m["date"][:10], "ctx": lg, "home": h, "away": a, "season": m.get("season"),
                            "referee": m.get("referee"), **r})

    # clubs from other leagues: their top-flight games (results only), and UEFA qualifiers
    euro_ids = {r["id"] for r in europe_rows}
    for g in sched_games:
        slug = g.get("league") or ""
        if g["id"] in euro_ids or slug in COVERED_SLUGS:
            continue
        if TOP_FLIGHT.match(slug):
            ctx = slug
        elif slug.startswith("uefa.") and slug.endswith("_qual"):
            ctx = EUROPE_CTX
        else:
            continue
        h, a = g["home"]["id"], g["away"]["id"]
        if ctx != EUROPE_CTX:
            groups.setdefault(h, slug)
            groups.setdefault(a, slug)
        names.setdefault(h, g["home"]["name"])
        names.setdefault(a, g["away"]["name"])
        matches.append({"date": g["date"][:10], "ctx": ctx, "home": h, "away": a, "hg": g["hg"], "ag": g["ag"],
                        "hc": None, "ac": None, "hcards": None, "acards": None, "hs": None, "as": None, "hst": None, "ast": None})

    # European matches, with stats
    for r in europe_rows:
        h, a = r["home"]["id"], r["away"]["id"]
        names.setdefault(h, r["home"]["name"])
        names.setdefault(a, r["away"]["name"])
        st = r.get("stats") or {}
        hs_, as_ = st.get("home") or {}, st.get("away") or {}

        def card(x):
            return None if x.get("yellow") is None or x.get("red") is None else x["yellow"] + x["red"]
        matches.append({"date": r["date"][:10], "ctx": EUROPE_CTX, "comp": r.get("comp"), "round": r.get("round"), "home": h, "away": a,
                        "hg": r["hg"], "ag": r["ag"], "hc": hs_.get("corners"), "ac": as_.get("corners"),
                        "hcards": card(hs_), "acards": card(as_), "hs": hs_.get("shots"), "as": as_.get("shots"),
                        "hst": hs_.get("sot"), "ast": as_.get("sot"), "id": r["id"]})
    for m in matches:
        for k in ("hc", "ac", "hcards", "acards", "hs", "as", "hst", "ast"):
            if m.get(k) is not None:
                m[k] = int(round(m[k]))
    matches.sort(key=lambda m: m["date"])
    return matches, groups, names


# ---------------------------------------------------------------- the rating model
class Ratings:
    """Penalised, time-weighted Poisson rating fit for one stat."""

    def __init__(self, half_life=300.0, tau=0.35, sigma=0.6, home_tau=0.15):
        self.half_life, self.tau, self.sigma, self.home_tau = half_life, tau, sigma, home_tau

    def fit(self, matches, groups, stat, asof):
        hk, ak = STATS[stat]
        ms = [m for m in matches if m["date"] < asof and has_stat(m, stat)]
        if not ms:
            raise ValueError("no data")
        teams = sorted({m["home"] for m in ms} | {m["away"] for m in ms})
        ti = {t: i for i, t in enumerate(teams)}
        gnames = sorted({groups.get(t, "other") for t in teams})
        gi = {g: i for i, g in enumerate(gnames)}
        cnames = sorted({m["ctx"] for m in ms})
        ci = {c: i for i, c in enumerate(cnames)}
        T, G, C = len(teams), len(gnames), len(cnames)
        H = np.array([ti[m["home"]] for m in ms])
        A = np.array([ti[m["away"]] for m in ms])
        X = np.array([ci[m["ctx"]] for m in ms])
        yh = np.array([m[hk] for m in ms], float)
        ya = np.array([m[ak] for m in ms], float)
        a0 = _d(asof).toordinal()
        age = np.array([a0 - _d(m["date"]).toordinal() for m in ms], float)
        w = 0.5 ** (age / self.half_life)
        tg = np.array([gi[groups.get(t, "other")] for t in teams])
        # starting values: context means
        mu0 = np.zeros(C)
        for c in range(C):
            s = X == c
            mu0[c] = math.log(max((yh[s].sum() + ya[s].sum()) / (2 * s.sum()), 0.05))

        x0 = np.concatenate([mu0, np.full(C, 0.1), np.zeros(2 * T + 2 * G)])
        it2, s2, h2 = 1 / self.tau ** 2, 1 / self.sigma ** 2, 1 / self.home_tau ** 2

        def unpack(x):
            mu, hm = x[:C], x[C:2 * C]
            att, dfn = x[2 * C:2 * C + T], x[2 * C + T:2 * C + 2 * T]
            ga, gd = x[2 * C + 2 * T:2 * C + 2 * T + G], x[2 * C + 2 * T + G:]
            return mu, hm, att, dfn, ga, gd

        def f(x):
            mu, hm, att, dfn, ga, gd = unpack(x)
            lh = mu[X] + hm[X] + att[H] - dfn[A]
            la = mu[X] + att[A] - dfn[H]
            eh, ea = np.exp(lh), np.exp(la)
            nll = np.sum(w * (eh - yh * lh)) + np.sum(w * (ea - ya * la))
            ra, rd = att - ga[tg], dfn - gd[tg]
            hbar = hm.mean()
            pen = 0.5 * it2 * (ra @ ra + rd @ rd) + 0.5 * s2 * (ga @ ga + gd @ gd) + 0.5 * h2 * np.sum((hm - hbar) ** 2)
            rh, rA = w * (eh - yh), w * (ea - ya)
            g_mu = np.bincount(X, rh + rA, C)
            g_hm = np.bincount(X, rh, C) + h2 * (hm - hbar)
            g_att = np.bincount(H, rh, T) + np.bincount(A, rA, T) + it2 * ra
            g_dfn = -np.bincount(A, rh, T) - np.bincount(H, rA, T) + it2 * rd
            g_ga = -it2 * np.bincount(tg, ra, G) + s2 * ga
            g_gd = -it2 * np.bincount(tg, rd, G) + s2 * gd
            return nll + pen, np.concatenate([g_mu, g_hm, g_att, g_dfn, g_ga, g_gd])

        res = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 600})
        mu, hm, att, dfn, ga, gd = unpack(res.x)
        self.stat, self.asof = stat, asof
        self.ctx = {c: (mu[i], hm[i]) for c, i in ci.items()}
        self.att = {t: att[i] for t, i in ti.items()}
        self.dfn = {t: dfn[i] for t, i in ti.items()}
        self.gatt = {g: ga[i] for g, i in gi.items()}
        self.gdfn = {g: gd[i] for g, i in gi.items()}
        self.groups = groups
        self.games = defaultdict(int)
        for m in ms:
            self.games[m["home"]] += 1
            self.games[m["away"]] += 1
        return self

    def team(self, t):
        g = self.groups.get(t, "other")
        return (self.att.get(t, self.gatt.get(g, 0.0)), self.dfn.get(t, self.gdfn.get(g, 0.0)))

    def expect(self, home, away, ctx=EUROPE_CTX):
        mu, hm = self.ctx.get(ctx, self.ctx.get(EUROPE_CTX))
        ah, dh = self.team(home)
        aa, da = self.team(away)
        return math.exp(mu + hm + ah - da), math.exp(mu + aa - dh)

    def venue(self, ctx=EUROPE_CTX):
        mu, hm = self.ctx.get(ctx, self.ctx.get(EUROPE_CTX))
        return math.exp(mu + hm), math.exp(mu)


# ---------------------------------------------------------------- the 60/40 predictor
class EuropePredictor:
    def __init__(self, params, tuning, rating_cfg=None):
        """params: model.core.Params (dc_rho, nb_alpha, blend_weight); tuning: dict with europe_* keys."""
        self.params = params
        self.t = tuning
        self.cfg = rating_cfg or {}

    def fit(self, matches, groups, asof):
        ratings = {s: Ratings(**self.cfg).fit(matches, groups, s, asof) for s in STATS}
        return self.attach(matches, groups, asof, ratings)

    def attach(self, matches, groups, asof, ratings):
        """Use already fitted ratings; index the games before `asof` by team (matches sorted by date)."""
        self.asof, self.groups, self.r = asof, groups, ratings
        self.by_team = defaultdict(list)
        for m in matches:
            if m["date"] >= asof:
                break
            self.by_team[m["home"]].append(m)
            self.by_team[m["away"]].append(m)
        return self

    def _form(self, team, stat, k):
        hk, ak = STATS[stat]
        r = self.r[stat]
        games = [m for m in self.by_team.get(team, ()) if has_stat(m, stat)][-5:]
        sf = ef = sa = ea = 0.0
        for m in games:
            lh, la = r.expect(m["home"], m["away"], m["ctx"])
            if m["home"] == team:
                sf, ef, sa, ea = sf + m[hk], ef + lh, sa + m[ak], ea + la
            else:
                sf, ef, sa, ea = sf + m[ak], ef + la, sa + m[hk], ea + lh
        return (sf + k) / (ef + k), (sa + k) / (ea + k), len(games)

    def predict(self, home, away, ctx=None, fast=False, labels=None):
        ctx = ctx or {}
        labels = labels or {}
        g = self.r["goals"]
        net = lambda t: g.team(t)[0] + g.team(t)[1]  # noqa: E731
        gap = net(home) - net(away)
        meetings = [m for m in self.by_team.get(home, ()) if away in (m["home"], m["away"])][-6:]
        w = self.params.blend_weight
        W = VIEW_WEIGHTS
        fk, hk2 = self.t.get("europe_form_k", 4.0), self.t.get("europe_h2h_k", 3.0)
        stats, base, views_all = {}, {}, {}
        for stat in STATS:
            r = self.r[stat]
            bh, ba = r.expect(home, away)
            vh, va = r.venue()
            base[stat] = (bh, ba)
            fa_h, fd_h, nh = self._form(home, stat, fk)
            fa_a, fd_a, na = self._form(away, stat, fk)
            form = (bh * fa_h * fd_a, ba * fa_a * fd_h)
            ch, ca = self.t.get("europe_gap_coef", {}).get(stat, (0.0, 0.0))
            gapv = (vh * math.exp(ch * gap), va * math.exp(ca * gap))
            hkk, akk = STATS[stat]
            rs = []
            for m in meetings:
                if not has_stat(m, stat):
                    continue
                mh_, ma_ = r.venue(m["ctx"])
                rs.append((m[hkk] / mh_, m[akk] / ma_) if m["home"] == home else (m[akk] / ma_, m[hkk] / mh_))
            n = len(rs)
            h2h = (vh * (sum(x[0] for x in rs) + hk2 * bh / vh) / (n + hk2),
                   va * (sum(x[1] for x in rs) + hk2 * ba / va) / (n + hk2))
            views = {"form": form, "gap": gapv, "h2h": h2h}
            mix = [sum(W[k] * views[k][j] for k in W) for j in (0, 1)]
            lh, la = (1 - w) * bh + w * mix[0], (1 - w) * ba + w * mix[1]
            views_all[stat] = (views, (nh, na), n, (lh, la))
        # adjustments (missing players) reuse the league model's rules
        from . import adjustments as adj
        adjs = []
        if ctx.get("home_missing") is not None:
            adjs += adj.absences(home, "home", "away", ctx["home_missing"], ctx.get("home_squad", {}))
        if ctx.get("away_missing") is not None:
            adjs += adj.absences(away, "away", "home", ctx["away_missing"], ctx.get("away_squad", {}))
        adjs += adj.congestion(ctx.get("home_rest_days"), False, "home", labels.get("home", home))
        adjs += adj.congestion(ctx.get("away_rest_days"), False, "away", labels.get("away", away))
        blended = {s: list(v[3]) for s, v in views_all.items()}
        final, mult = adj.apply(blended, adjs)
        for stat, (lh, la) in final.items():
            if stat == "goals":
                probs = goal_probabilities(lh, la, self.params.dc_rho)
            else:
                probs = count_probabilities(stat, lh, la, self.t.get("europe_nb_alpha", {}).get(stat, self.params.nb_alpha[stat]))
            views, (nh, na), n, (bl_h, bl_a) = views_all[stat]
            stats[stat] = {"home": lh, "away": la, "total": lh + la, "base_home": base[stat][0], "base_away": base[stat][1],
                           "blend_home": bl_h, "blend_away": bl_a, **probs}
            if not fast:
                stats[stat]["views"] = {k: list(v) for k, v in views.items()}
                stats[stat]["view_meta"] = {"form_games": [nh, na], "h2h_meetings": n}
                stats[stat]["why"] = self.why(stat, home, away, labels)
        out = {"home": home, "away": away, "league": "europe", "stats": stats}
        if fast:
            return out
        gh, ga_ = g.games.get(home, 0), g.games.get(away, 0)
        out["adjustments"] = [a.to_dict() for a in adjs]
        out["sample"] = {"home_games": gh, "away_games": ga_, "home_prior": "league level", "away_prior": "league level"}
        out["basis"] = {"min_games": min(gh, ga_), "team_news": bool(ctx.get("injuries_known")),
                        "adjusted_max_pct": round(max(abs(m - 1) for pair in mult.values() for m in pair) * 100, 1)}
        out["blend"] = {"base_weight": 1 - w, "views_weight": w, "weights": W, "gap": gap,
                        "strength": [net(home), net(away)],
                        "h2h": [{"date": m["date"], "home": m["home"], "away": m["away"], "score": [m["hg"], m["ag"]]}
                                for m in reversed(meetings)]}
        out["groups"] = [self.groups.get(home, "other"), self.groups.get(away, "other")]
        out["analyst_view"] = []
        return out

    def why(self, stat, home, away, labels):
        r = self.r[stat]
        vh, va = r.venue()
        lab = {"goals": "goals", "corners": "corners", "cards": "cards", "shots": "shots", "shots_on_target": "shots on target"}[stat]
        hn, an = labels.get("home", home), labels.get("away", away)
        ah, dh = r.team(home)
        aa, da = r.team(away)
        lines = [
            (abs(ah), f"{hn}: {math.exp(ah):.2f}x the {lab} of an average side (rating from {r.games.get(home, 0)} games)"),
            (abs(dh), f"{hn} allow {1 / math.exp(dh):.2f}x the usual {lab}"),
            (abs(aa), f"{an}: {math.exp(aa):.2f}x the {lab} of an average side (rating from {r.games.get(away, 0)} games)"),
            (abs(da), f"{an} allow {1 / math.exp(da):.2f}x the usual {lab}"),
        ]
        lines.sort(key=lambda x: -x[0])
        out = [t for _, t in lines[:3]]
        out.append(f"European average: {vh:.1f} for home teams, {va:.1f} for away teams")
        return out


# ---------------------------------------------------------------- tuning helpers (used by backtest/europe.py)
def fit_gap(predictors_by_date, europe_matches):
    """Strength-gap effects: log(value / European venue average) against the pre-match goal-rating gap."""
    num = {s: [0.0, 0.0] for s in STATS}
    den = {s: [0.0, 0.0] for s in STATS}
    for m in europe_matches:
        p = predictors_by_date.get(m["date"])
        if not p:
            continue
        g = p.r["goals"]
        gap = sum(g.team(m["home"])) - sum(g.team(m["away"]))
        for s, (hk, ak) in STATS.items():
            if not has_stat(m, s):
                continue
            vh, va = p.r[s].venue()
            for j, (x, mu) in enumerate(((m[hk], vh), (m[ak], va))):
                num[s][j] += gap * math.log((x + 0.5) / (mu + 0.5))
                den[s][j] += gap * gap
    return {s: [round(num[s][j] / den[s][j], 4) if den[s][j] else 0.0 for j in (0, 1)] for s in STATS}


LINES = LINES  # re-exported for callers
