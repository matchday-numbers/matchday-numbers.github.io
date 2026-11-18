"""Our take: the numbers adjusted by the subjective view (owner's choice, 15 Nov 2026).

The subjective view (data/overrides/analyst.json, tools/analyst_rules.md) is written only for matches in
the next JUDGE_HOURS. For each stat it gives a lean (higher / lower / same) and a size, `adjust_pct`:
how far the analyst would move the expected total (at most MAX_PCT either way). Our take multiplies both
teams' expected numbers by (1 + adjust_pct / 100) and recomputes every probability with the same
distributions as the numbers (Dixon-Coles for goals, negative binomial for the rest), so the line
percentages, the range and the most likely scores all follow the judgement.

The numbers alone are kept unchanged in prediction["stats"] (shown under each stat's "Why" and scored
in the track record); the take is stored next to them in prediction["take"] and scored separately.
"""
from __future__ import annotations

from .core import STATS, count_probabilities, goal_probabilities

JUDGE_HOURS = 96      # subjective views (and so the take) only for matches kicking off within this many hours
MAX_PCT = 25.0        # largest move a judgement may make, either way
DEFAULT_PCT = 5.0     # size used when an older view gives a lean but no size


def view_pct(v):
    """(adjust_pct, sized) for one stat's view: the size, forced to agree with the lean."""
    if not isinstance(v, dict):
        return 0.0, False
    lean = v.get("lean")
    sign = 1 if lean == "higher" else -1 if lean == "lower" else 0
    p = v.get("adjust_pct")
    if isinstance(p, (int, float)) and not isinstance(p, bool) and p == p:  # p == p: not NaN
        p = min(abs(float(p)), MAX_PCT)
        return sign * p, True
    return sign * DEFAULT_PCT, False


def apply(stats, view, rho, alpha_of):
    """Take for every stat. stats: prediction["stats"]; view: the match's analyst view (or None);
    rho: Dixon-Coles rho; alpha_of(stat): negative binomial alpha. Returns None without a view."""
    if not view or not isinstance(view, dict):
        return None
    out = {"applied": False, "written_at": view.get("written_at")}
    for stat in STATS:
        s = stats[stat]
        pct, sized = view_pct(view.get(stat))
        f = 1 + pct / 100
        lh, la = s["home"] * f, s["away"] * f
        if stat == "goals":
            probs = goal_probabilities(lh, la, rho)
        else:
            probs = count_probabilities(stat, lh, la, alpha_of(stat))
        out[stat] = {"home": lh, "away": la, "total": lh + la, "adjust_pct": pct, "sized": sized,
                     "lean": (view.get(stat) or {}).get("lean") if isinstance(view.get(stat), dict) else None, **probs}
        out["applied"] = out["applied"] or pct != 0
    return out


def merged(stats, take):
    """Stats as published: the take's numbers over the numbers alone (reasoning etc. kept)."""
    if not take:
        return stats
    return {k: {**v, **(take.get(k) or {})} for k, v in stats.items()}
