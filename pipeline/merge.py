"""Merges football-data.co.uk and ESPN records of the same match and cross-checks them.

Per stat, a match gets one of:
  verified     both sources agree (corners/cards/shots: within 1)
  single       only one source has it yet (it is used, and labelled)
  conflict     sources disagree by more than the tolerance: the stat is shown with both
               values and EXCLUDED from the model for that match
"""
from __future__ import annotations

from datetime import date

# (model key home, model key away, ESPN team-stat key, tolerance)
CHECKS = {
    "goals": ("hg", "ag", None, 0),
    "corners": ("hc", "ac", "corners", 1),
    "yellow": ("hy", "ay", "yellow", 1),
    "red": ("hr", "ar", "red", 0),
    "shots": ("hs", "as", "shots", 2),
    "sot": ("hst", "ast", "sot", 1),
}


def _espn_val(ev, summ, side, key):
    if key is None:
        return ev.get("hg") if side == "home" else ev.get("ag")
    v = ((summ or {}).get("teams") or {}).get(side, {}).get(key)
    return None if v is None else int(round(v))


def record_from_espn(league, season, ev, summ, home, away):
    m = {"date": ev["kickoff"][:10], "league": league, "season": season, "home": home, "away": away,
         "referee": None, "hg": ev["hg"], "ag": ev["ag"]}
    for _, (hk, ak, key, _) in CHECKS.items():
        if key:
            m[hk] = _espn_val(ev, summ, "home", key)
            m[ak] = _espn_val(ev, summ, "away", key)
    return m


def finish(m):
    m["hcards"] = None if m.get("hy") is None or m.get("hr") is None else m["hy"] + m["hr"]
    m["acards"] = None if m.get("ay") is None or m.get("ar") is None else m["ay"] + m["ar"]
    return m


def merge_league(league, season, fd_matches, espn_events, summaries, fd_of_espn, primary="football-data.co.uk"):
    """Returns (matches, report). Each match carries `checks`, `sources` and ESPN ids.
    `primary` names the first source (football-data.co.uk, or FotMob for MLS)."""
    espn_done = [e for e in espn_events if e.get("completed")]
    used = set()
    out = []
    report = {"verified": 0, "single": 0, "conflict": 0, "conflicts": []}

    def find(m):
        d = date.fromisoformat(m["date"])
        for e in espn_done:
            if e["espn_id"] in used:
                continue
            if fd_of_espn.get(e["home"]["espn_id"]) == m["home"] and fd_of_espn.get(e["away"]["espn_id"]) == m["away"]:
                if abs((date.fromisoformat(e["kickoff"][:10]) - d).days) <= 1:
                    return e
        return None

    for m in fd_matches:
        rec = dict(m)
        e = find(m)
        rec["checks"] = {}
        rec["sources"] = [primary]
        if e:
            used.add(e["espn_id"])
            s = summaries.get(e["espn_id"])
            rec.update({"espn_id": e["espn_id"], "kickoff": e["kickoff"], "venue": (s or {}).get("venue") or e.get("venue")})
            rec["sources"].append("ESPN")
            for stat, (hk, ak, key, tol) in CHECKS.items():
                fh, fa = m.get(hk), m.get(ak)
                eh, ea = _espn_val(e, s, "home", key), _espn_val(e, s, "away", key)
                if fh is None and eh is not None:
                    rec[hk], rec[ak] = eh, ea
                    rec["checks"][stat] = "single"
                elif eh is None or (s is None and key is not None):
                    rec["checks"][stat] = "single"
                elif abs(fh - eh) <= tol and abs(fa - ea) <= tol:
                    rec["checks"][stat] = "verified"
                else:
                    rec["checks"][stat] = "conflict"
                    rec.setdefault("conflict_values", {})[stat] = {primary: [fh, fa], "ESPN": [eh, ea]}
                    report["conflicts"].append(f"{m['date']} {m['home']}-{m['away']} {stat}: {primary} {fh}-{fa} vs ESPN {eh}-{ea}")
                    if stat != "goals":
                        rec[hk] = rec[ak] = None   # excluded from the model
        else:
            for stat in CHECKS:
                rec["checks"][stat] = "single"
        out.append(finish(rec))

    # ESPN-only matches (first source not updated yet)
    for e in espn_done:
        if e["espn_id"] in used:
            continue
        home, away = fd_of_espn.get(e["home"]["espn_id"]), fd_of_espn.get(e["away"]["espn_id"])
        if not home or not away:
            continue
        s = summaries.get(e["espn_id"])
        rec = record_from_espn(league, season, e, s, home, away)
        rec.update({"espn_id": e["espn_id"], "kickoff": e["kickoff"], "venue": (s or {}).get("venue") or e.get("venue"),
                    "sources": ["ESPN"], "checks": {k: "single" for k in CHECKS}})
        out.append(finish(rec))

    for r in out:
        vals = list(r["checks"].values())
        if "conflict" in vals:
            report["conflict"] += 1
        elif all(v == "verified" for v in vals):
            report["verified"] += 1
        else:
            report["single"] += 1
    out.sort(key=lambda r: (r["date"], r.get("kickoff") or "", r["home"]))
    return out, report


def europe_records(league, espn_events, summaries, season):
    """European competition matches: ESPN only (football-data.co.uk doesn't cover them)."""
    out = []
    for e in espn_events:
        if not e.get("completed"):
            continue
        s = summaries.get(e["espn_id"])
        rec = record_from_espn(league, season, e, s, e["home"]["espn_id"], e["away"]["espn_id"])
        rec.update({"espn_id": e["espn_id"], "kickoff": e["kickoff"], "venue": (s or {}).get("venue") or e.get("venue"),
                    "sources": ["ESPN"], "checks": {k: "single" for k in CHECKS}, "round": e.get("round")})
        out.append(finish(rec))
    out.sort(key=lambda r: r["kickoff"])
    return out
