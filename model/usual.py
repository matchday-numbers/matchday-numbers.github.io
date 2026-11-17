"""What usually happens: how often games in a competition go over each line (fix 5(b), 17 Nov 2026).

Each stat's verdict line ("The numbers:" / "Our take:") highlights the shown line where this match differs
MOST from a usual game in the same competition, instead of the tightest line at 60%+, which mostly repeated
the base rate (e.g. "over 1.5 goals, 77%" when 77% of games go over anyway).

Rules (the site's app.js `standout` mirrors these; keep them in step):
- usual rate = share of games in the competition, last season and this one, that went over the line;
- a line counts only if this match differs from the usual rate by at least MIN_GAP (6 points);
- the call must be more likely than not (> 50%): over when the match is above usual, under when below;
- the biggest difference wins (ties: the more likely call);
- no line qualifies -> "about a usual game" (with the competition's average);
- fewer than MIN_GAMES games with the stat -> no usual rates (the site falls back to the 60% rule).
"""
from __future__ import annotations

from .core import STATS

MIN_GAP = 0.06
MIN_GAMES = 100


def histograms(matches, since, key_of):
    """{comp: {"since", stat: {"n", "mean", "hist": {total: games}}}} from model match records.
    key_of(match) -> competition key or None (skipped)."""
    out = {}
    for m in matches:
        if (m.get("date") or "") < since:
            continue
        comp = key_of(m)
        if not comp:
            continue
        c = out.setdefault(comp, {"since": since})
        for stat, (hk, ak) in STATS.items():
            hv, av = m.get(hk), m.get(ak)
            if hv is None or av is None:
                continue
            tot = int(round(hv + av))
            s = c.setdefault(stat, {"n": 0, "sum": 0, "hist": {}})
            s["n"] += 1
            s["sum"] += tot
            s["hist"][str(tot)] = s["hist"].get(str(tot), 0) + 1
    for c in out.values():
        for stat in STATS:
            s = c.get(stat)
            if not s:
                continue
            s["mean"] = round(s.pop("sum") / s["n"], 2)
            if s["n"] < MIN_GAMES:
                del c[stat]
    return out


def rate(h, line):
    """Share of games that went over `line` (h = one stat's entry from histograms)."""
    n = h["n"]
    return sum(c for t, c in h["hist"].items() if int(t) > float(line)) / n if n else None


def standout(over_show, h):
    """The highlighted call for one stat. over_show: {line: P(over)}; h: usual histogram or None.
    Returns None (no usual rates), {"usual_game": True, "mean": ...} or
    {"side": "over"/"under", "line": str, "p": P(call), "usual": usual rate of that side, "gap": points}."""
    if not h:
        return None
    best = None
    for line, p in over_show.items():
        u = rate(h, line)
        if u is None:
            continue
        for side, pc, uc in (("over", p, u), ("under", 1 - p, 1 - u)):
            gap = pc - uc
            if gap >= MIN_GAP and pc > 0.5:
                cand = {"side": side, "line": str(line), "p": pc, "usual": uc, "gap": gap}
                if not best or (gap, pc) > (best["gap"], best["p"]):
                    best = cand
    return best or {"usual_game": True, "mean": h["mean"]}
