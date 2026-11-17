"""Prediction model core.

Step 1  statistical base: league venue averages x team attack x opponent defence,
        recency-weighted, shrunk toward a prior (last season, or a promoted-team prior).
Step 2  adjustments, each kept separate with its own effect (see adjustments.py).
Step 3  probabilities: Dixon-Coles for goals, negative binomial for count stats.

Matches are plain dicts with keys:
  date (YYYY-MM-DD), league, season, home, away, referee,
  hg, ag, hs, as, hst, ast, hc, ac, hy, ay, hr, ar, hcards, acards
Missing stats are None; a match missing a stat is skipped for that stat only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

STATS = {
    "goals": ("hg", "ag"),
    "corners": ("hc", "ac"),
    "cards": ("hcards", "acards"),
    "shots": ("hs", "as"),
    "shots_on_target": ("hst", "ast"),
}

LINES = {
    "goals": [1.5, 2.5, 3.5],
    "corners": [8.5, 9.5, 10.5, 11.5],
    "cards": [3.5, 4.5, 5.5],
    "shots": [20.5, 23.5, 26.5],
    "shots_on_target": [6.5, 8.5, 10.5],
}

# Lines shown on the site (owner, 16 Nov 2026): five, centred on each match's expected total, this far apart.
# LINES above stay fixed for scoring, so the track record stays comparable over time.
SHOW_STEP = {"goals": 1, "corners": 1, "cards": 1, "shots": 3, "shots_on_target": 1}
SHOW_COUNT = 5


def show_lines(stat, total):
    """Five lines centred on the expected total (middle = the nearest x.5), never below 0.5."""
    step = SHOW_STEP[stat]
    mid = math.floor(total) + 0.5
    lo = max(0.5, mid - step * (SHOW_COUNT // 2))
    return [lo + step * i for i in range(SHOW_COUNT)]


# Used only when there is no data at all for a league yet.
DEFAULT_MEANS = {
    "goals": (1.5, 1.2),
    "corners": (5.4, 4.5),
    "cards": (2.0, 2.3),
    "shots": (13.5, 11.0),
    "shots_on_target": (4.7, 3.8),
}

DEFAULT_PROMOTED = {
    "goals": (0.82, 1.18),
    "corners": (0.9, 1.08),
    "cards": (1.03, 1.0),
    "shots": (0.88, 1.12),
    "shots_on_target": (0.85, 1.15),
}


@dataclass
class Params:
    recent_n: int = 6
    recent_weight: float = 2.0
    shrink_k: dict = field(default_factory=lambda: {
        "goals": 8.0, "corners": 8.0, "cards": 8.0, "shots": 6.0, "shots_on_target": 6.0})
    prior_regress: dict = field(default_factory=lambda: {
        "goals": 0.7, "corners": 0.7, "cards": 0.7, "shots": 0.7, "shots_on_target": 0.7})
    venue_blend: float = 0.0
    goals_sot_mix: float = 0.0   # share of goals attack/defence taken from shots-on-target strength
    blend_weight: float = 0.0    # share given to form, team gap and head-to-head; tuned.json sets the user's 0.4
    league_prior_matches: float = 80.0
    dc_rho: float = -0.06
    # NB over-dispersion for match totals: var = m + alpha * m^2 (0 = Poisson)
    nb_alpha: dict = field(default_factory=lambda: {
        "goals": 0.0, "corners": 0.03, "cards": 0.05, "shots": 0.03, "shots_on_target": 0.04})


def _val(m, key):
    v = m.get(key)
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def has_stat(m, stat):
    hk, ak = STATS[stat]
    return _val(m, hk) is not None and _val(m, ak) is not None


# ---------------------------------------------------------------- league means
def league_means(cur, prev, stat, params: Params):
    """Venue averages (home team's stat, away team's stat) per match, stabilised early
    in the season by blending with last season's averages."""
    hk, ak = STATS[stat]
    c = [m for m in cur if has_stat(m, stat)]
    p = [m for m in (prev or []) if has_stat(m, stat)]
    n = len(c)
    if p:
        ph = sum(m[hk] for m in p) / len(p)
        pa = sum(m[ak] for m in p) / len(p)
    elif n:
        ph = sum(m[hk] for m in c) / n
        pa = sum(m[ak] for m in c) / n
    else:
        ph, pa = DEFAULT_MEANS[stat]
    k = params.league_prior_matches if (p or not n) else 0.0
    mh = (sum(m[hk] for m in c) + k * ph) / (n + k) if (n + k) else ph
    ma = (sum(m[ak] for m in c) + k * pa) / (n + k) if (n + k) else pa
    return max(mh, 1e-6), max(ma, 1e-6)


# ---------------------------------------------------------------- team strength
def team_records(matches, team, stat):
    """[(venue, for, against, date)] in date order."""
    hk, ak = STATS[stat]
    out = []
    for m in matches:
        if not has_stat(m, stat):
            continue
        if m["home"] == team:
            out.append(("H", m[hk], m[ak], m["date"]))
        elif m["away"] == team:
            out.append(("A", m[ak], m[hk], m["date"]))
    out.sort(key=lambda r: r[3])
    return out


def _weighted_ratio(recs, mh, ma, params, prior, k):
    n = len(recs)
    sw = s_att = s_def = 0.0
    for i, (v, f, a, _) in enumerate(recs):
        w = params.recent_weight if i >= n - params.recent_n else 1.0
        exp_for = mh if v == "H" else ma
        exp_against = ma if v == "H" else mh
        s_att += w * f / exp_for
        s_def += w * a / exp_against
        sw += w
    att = (s_att + k * prior[0]) / (sw + k)
    dfn = (s_def + k * prior[1]) / (sw + k)
    return att, dfn


def strength(recs, mh, ma, prior, params: Params, stat, venue):
    """Attack/defence multipliers for a team playing at `venue` ('H' or 'A')."""
    k = params.shrink_k[stat]
    att, dfn = _weighted_ratio(recs, mh, ma, params, prior, k)
    if params.venue_blend > 0:
        vrecs = [r for r in recs if r[0] == venue]
        v_att, v_def = _weighted_ratio(vrecs, mh, ma, params, (att, dfn), k)
        b = params.venue_blend
        att = (1 - b) * att + b * v_att
        dfn = (1 - b) * dfn + b * v_def
    return att, dfn


def season_ratios(season_matches, stat, params: Params):
    """Full-season (unweighted) attack/defence ratios per team."""
    mh, ma = league_means(season_matches, None, stat, Params(league_prior_matches=0))
    hk, ak = STATS[stat]
    acc = {}
    for m in season_matches:
        if not has_stat(m, stat):
            continue
        for team, f, a, ef, ea in ((m["home"], m[hk], m[ak], mh, ma),
                                   (m["away"], m[ak], m[hk], ma, mh)):
            s = acc.setdefault(team, [0.0, 0.0, 0])
            s[0] += f / ef
            s[1] += a / ea
            s[2] += 1
    return {t: (s[0] / s[2], s[1] / s[2]) for t, s in acc.items() if s[2]}


def promoted_prior(seasons_in_order, stat, params: Params):
    """Average first-season ratios of promoted teams, from pairs of consecutive seasons."""
    vals = []
    for prev, cur in zip(seasons_in_order, seasons_in_order[1:]):
        prev_teams = {m["home"] for m in prev} | {m["away"] for m in prev}
        r = season_ratios(cur, stat, params)
        vals += [v for t, v in r.items() if t not in prev_teams]
    if len(vals) < 3:
        return DEFAULT_PROMOTED[stat]
    return (sum(v[0] for v in vals) / len(vals), sum(v[1] for v in vals) / len(vals))


def team_prior(team, prev_ratios, promoted, regress):
    if team in prev_ratios:
        a, d = prev_ratios[team]
        return 1 + regress * (a - 1), 1 + regress * (d - 1)
    return promoted


# ---------------------------------------------------------------- distributions
def poisson_pmf(k, lam):
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1)) if lam > 0 else (1.0 if k == 0 else 0.0)


def score_matrix(lh, la, rho, max_goals=10):
    m = [[poisson_pmf(i, lh) * poisson_pmf(j, la) for j in range(max_goals + 1)]
         for i in range(max_goals + 1)]
    tau = {(0, 0): 1 - lh * la * rho, (0, 1): 1 + lh * rho, (1, 0): 1 + la * rho, (1, 1): 1 - rho}
    for (i, j), t in tau.items():
        m[i][j] *= max(t, 0.0)
    s = sum(map(sum, m))
    return [[x / s for x in row] for row in m]


def nb_pmf_list(mean, alpha, kmax):
    """P(X=k) for k=0..kmax; negative binomial with var = mean + alpha*mean^2."""
    if mean <= 0:
        return [1.0] + [0.0] * kmax
    if alpha <= 1e-9:
        return [poisson_pmf(k, mean) for k in range(kmax + 1)]
    r = 1.0 / alpha
    p = r / (r + mean)
    out = []
    for k in range(kmax + 1):
        out.append(math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                            + r * math.log(p) + k * math.log(1 - p)))
    return out


def quantile(pmf, q):
    c = 0.0
    for k, p in enumerate(pmf):
        c += p
        if c >= q:
            return k
    return len(pmf) - 1


TAKE_P = 0.80  # the take: a line (over or under) with at least this chance (owner, 17 Nov 2026)


def take_line(pmf, shown):
    """Take candidates for one stat, from the full distribution: for each side ("over", "under") the tightest
    line with at least TAKE_P chance (closest to TAKE_P, so the most informative), taken from the shown lines
    when one of them reaches TAKE_P, else from beyond them (shown=False: the site adds it as an extra row).
    Returns {"over": {"line", "p", "shown"} or None, "under": ...}. Which side is the take is chosen by
    model/usual.py pick_take (and app.js takeLine): the side where the match beats a usual game by more."""
    tail = [0.0] * (len(pmf) + 1)  # tail[k] = P(total >= k)
    for k in range(len(pmf) - 1, -1, -1):
        tail[k] = tail[k + 1] + pmf[k]

    def p_of(side, line):
        k = int(line) + 1                           # over x.5 = total >= x+1
        o = tail[k] if k < len(tail) else 0.0
        return o if side == "over" else 1 - o

    out = {}
    every = [k + 0.5 for k in range(len(pmf))]
    for side in ("over", "under"):
        best = None
        for lines, on in (([float(x) for x in shown], True), (every, False)):
            c = [(round(p_of(side, l), 9), l) for l in lines]
            c = [x for x in c if x[0] >= TAKE_P - 1e-9]
            if c:
                q, l = min(c)
                best = {"line": str(l), "p": q, "shown": on}
                break
        out[side] = best
    return out


def goal_probabilities(lh, la, rho):
    m = score_matrix(lh, la, rho)
    n = len(m)
    home = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    draw = sum(m[i][i] for i in range(n))
    away = 1 - home - draw
    totals = [0.0] * (2 * n)
    for i in range(n):
        for j in range(n):
            totals[i + j] += m[i][j]
    over = {str(l): sum(p for k, p in enumerate(totals) if k > l) for l in LINES["goals"]}
    over_show = {str(l): sum(p for k, p in enumerate(totals) if k > l) for l in show_lines("goals", lh + la)}
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))
    scores = sorted(((m[i][j], f"{i}-{j}") for i in range(n) for j in range(n)), reverse=True)[:5]
    clean_home = sum(m[i][0] for i in range(n))  # home keeps clean sheet
    clean_away = sum(m[0][j] for j in range(n))
    return {
        "home_win": home, "draw": draw, "away_win": away,
        "over": over, "over_show": over_show, "btts": btts,
        "likely_scores": [{"score": s, "p": p} for p, s in scores],
        "clean_sheet_home": clean_home, "clean_sheet_away": clean_away,
        "range": [quantile(totals, 0.1), quantile(totals, 0.9)],
        "take_line": take_line(totals, over_show),
    }


def count_probabilities(stat, lh, la, alpha):
    mean = lh + la
    kmax = int(mean * 4 + 30)
    pmf = nb_pmf_list(mean, alpha, kmax)
    over = {str(l): sum(p for k, p in enumerate(pmf) if k > l) for l in LINES[stat]}
    over_show = {str(l): sum(p for k, p in enumerate(pmf) if k > l) for l in show_lines(stat, mean)}
    return {"over": over, "over_show": over_show, "range": [quantile(pmf, 0.1), quantile(pmf, 0.9)],
            "take_line": take_line(pmf, over_show)}
