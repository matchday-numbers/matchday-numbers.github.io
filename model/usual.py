"""What usually happens: how often games in a competition go over each line (17 Nov 2026).

usual rate = share of games in the competition, last season and this one, that went over the line. The site
shows it next to every line ("usual NN%" and a faint tick) and next to the take (model/core.py take_line,
the line with 80%+ chance), so a reader can tell a real signal from what happens anyway.
Fewer than MIN_GAMES games with a stat -> no usual rates for it.
"""
from __future__ import annotations

from .core import STATS

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


def pick_take(cands, h=None):
    """The take from model/core.py take_line candidates: shown lines first; then the side where this match beats
    a usual game in the competition by more (h = usual histogram; so an 80% under line that is LESS likely than
    usual never wins over an over line well above usual); without usual rates, the tightest; ties go to the over.
    Returns {"side", "line", "p", "shown"} or None. app.js takeLine mirrors this."""
    c = [{"side": side, **v} for side, v in (cands or {}).items() if v]
    if not c:
        return None
    if any(x["shown"] for x in c):
        c = [x for x in c if x["shown"]]

    def edge(x):
        if not h:
            return -x["p"]
        r = rate(h, x["line"])
        return x["p"] - (r if x["side"] == "over" else 1 - r)
    return max(c, key=lambda x: (round(edge(x), 9), x["side"] == "over"))
