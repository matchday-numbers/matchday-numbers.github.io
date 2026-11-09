"""Validates subjective views (tools/analyst_rules.md) and merges them into data/overrides/analyst.json.

  python tools/analyst_merge.py --check FILE...     validate only (exit 1 if any entry has a problem)
  python tools/analyst_merge.py FILE...             validate, merge the valid entries, prune old ones,
                                                    and report coverage of the matches the site posts
  python tools/analyst_merge.py --coverage          coverage report only
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "overrides", "analyst.json")
STATS = ["goals", "corners", "cards", "shots", "shots_on_target"]
FORBIDDEN = re.compile(r"\b(lock|locks|sure thing|guarantee[ds]?|banker|nailed[- ]on|bet|bets|betting|wager)\b", re.I)
BETTING_SITE = re.compile(r"(bet365|betexplorer|oddschecker|oddsportal|williamhill|betfair|paddypower|skybet|draftkings|fanduel|"
                          r"betway|unibet|bwin|888sport|ladbrokes|coral\.co|betmgm|caesars|pointsbet|bovada|1xbet|stake\.com|"
                          r"tipster|betting|freebet|bettingexpert|forebet|predictz|windrawwin)", re.I)


def ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def problems(e):
    out = []
    if not isinstance(e, dict):
        return ["not an object"]
    ov = e.get("overall")
    if not isinstance(ov, str) or len(ov) < 60:
        out.append("overall missing or too short")
    for s in STATS:
        x = e.get(s)
        if not isinstance(x, dict):
            out.append(f"{s} missing")
            continue
        if x.get("lean") not in ("higher", "lower", "same"):
            out.append(f"{s}.lean must be higher/lower/same")
        c = x.get("call")
        if not isinstance(c, str) or not 2 <= len(c.strip()) <= 48 or "%" in c:
            out.append(f"{s}.call missing, too long or has a percentage")
        t = x.get("text")
        if not isinstance(t, str) or len(t.strip()) < 40:
            out.append(f"{s}.text missing or too short")
    src = e.get("sources")
    if not isinstance(src, list) or not src or not all(isinstance(u, str) and u.startswith("http") for u in src):
        out.append("sources must be a non-empty list of URLs")
    elif any(BETTING_SITE.search(u) for u in src):
        out.append("betting site in sources")
    text = " ".join([str(e.get("overall", ""))] + [str((e.get(s) or {}).get(k, "")) for s in STATS for k in ("call", "text")])
    m = FORBIDDEN.search(text)
    if m:
        out.append(f"wording not allowed: {m.group(0)!r}")
    if e.get("written_at"):
        try:
            ts(e["written_at"])
        except ValueError:
            out.append("written_at is not an ISO time")
    return out


def posted():
    """{match id: kickoff} for every upcoming match the site shows with an estimate."""
    meta = json.load(open(os.path.join(ROOT, "site", "data", "meta.json")))
    out = {}
    for lg in meta["leagues"]:
        try:
            L = json.load(open(os.path.join(ROOT, "site", "data", f"league-{lg['key']}.json")))
        except (OSError, ValueError):
            continue
        for u in L.get("upcoming", []):
            if u.get("prediction"):
                out[u["id"]] = u["kickoff"]
    return out


def kickoffs():
    out = {}
    for f in glob.glob(os.path.join(ROOT, "data", "predictions", "*", "*", "*.json")):
        out[os.path.basename(f)[:-5]] = None
    for f in glob.glob(os.path.join(ROOT, "data", "predictions", "*", "*", "*.json")):
        try:
            out[os.path.basename(f)[:-5]] = json.load(open(f))["kickoff"]
        except (OSError, ValueError, KeyError):
            pass
    return out


def coverage(views):
    now = datetime.now(timezone.utc)
    ps = posted()
    missing = [i for i in ps if i not in views]
    stale = [i for i, ko in ps.items() if i in views and ts(ko) - now <= timedelta(hours=36)
             and now - ts(views[i].get("written_at") or "2000-01-01T00:00:00+00:00") >= timedelta(hours=18)]
    print(f"coverage: {len(ps) - len(missing)} of {len(ps)} posted matches have a subjective view; "
          f"{len(missing)} missing, {len(stale)} due a refresh (kick-off within 36 h, view older than 18 h)")
    return missing, stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args()
    store = json.load(open(PATH)) if os.path.exists(PATH) else {"matches": {}}
    views = store.setdefault("matches", {})
    if a.coverage:
        coverage(views)
        return
    now = datetime.now(timezone.utc)
    good, bad = {}, 0
    for f in a.files:
        try:
            data = json.load(open(f))
        except (OSError, ValueError) as ex:
            print(f"{f}: unreadable ({ex})")
            bad += 1
            continue
        for mid, e in (data.get("matches") or {}).items():
            pr = problems(e)
            if pr:
                bad += 1
                print(f"{f} {mid}: " + "; ".join(pr))
            else:
                e.setdefault("written_at", now.isoformat(timespec="seconds"))
                good[str(mid)] = e
    print(f"{len(good)} valid views, {bad} with problems")
    if a.check:
        sys.exit(1 if bad else 0)
    views.update(good)
    ko = kickoffs()
    for mid in list(views):
        k = ko.get(mid)
        w = views[mid].get("written_at")
        if (k and now - ts(k) > timedelta(days=3)) or (not k and w and now - ts(w) > timedelta(days=40)):
            del views[mid]
    with open(PATH, "w") as f:
        json.dump(store, f, indent=1, ensure_ascii=False)
    print(f"analyst.json now holds {len(views)} views")
    coverage(views)


if __name__ == "__main__":
    main()
