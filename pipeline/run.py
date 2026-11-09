"""One update run: fetch -> merge & cross-check -> predict & freeze -> score -> write site data.

  python -m pipeline.run            # normal run (GitHub Actions, every few hours)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import sys
import traceback
import unicodedata
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.data import load_file  # noqa: E402
from model.adjustments import is_derby  # noqa: E402
from pipeline import fotmob_stats, merge, players, predictions, site_data, sources, teams  # noqa: E402

try:  # the estimate engine needs numpy/scipy; stats must still publish without it
    from pipeline import engine, europe  # noqa: E402
except Exception as _ex:  # pragma: no cover
    engine = europe = None
    _ENGINE_IMPORT_ERROR = repr(_ex)
from pipeline.sources import DOMESTIC, EUROPE, LEAGUES, PREDICTED  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HISTORY = os.path.join(DATA, "history")
UPCOMING_DAYS = 31


def jload(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def model_version():
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(ROOT, "model", "*.py"))) + sorted(glob.glob(os.path.join(ROOT, "model", "tuned*.json"))):
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:10]


def season_start(season, league):
    y = 2000 + int(season[:2])
    if league == "mls":
        # MLS played calendar years until 2026; from 2027-28 it runs July-May like Europe. The 2026-27
        # window keeps the whole 2026 season (from February) and the short spring 2027 season.
        return date(y, 2, 1) if season <= "2627" else date(y, 7, 1)
    return date(y, 9, 1) if league in EUROPE else date(y, 7, 25)


def season_window(season):
    """July-June dates a season label covers in data/history files."""
    y = 2000 + int(season[:2])
    return date(y, 7, 1), date(y + 1, 7, 1)


def copy_season_rows(src, dst, season):
    """Copies a football-data.co.uk-style CSV, keeping only the season's July-June rows."""
    import csv
    lo, hi = season_window(season)
    with open(src, encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))
    keep = []
    for r in rows:
        try:
            d = datetime.strptime((r.get("Date") or "").strip(), "%d/%m/%Y").date()
        except ValueError:
            try:
                d = datetime.strptime((r.get("Date") or "").strip(), "%d/%m/%y").date()
            except ValueError:
                continue
        if lo <= d < hi:
            keep.append(r)
    if rows:
        with open(dst, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(keep)


def history_seasons(league, season):
    """Complete earlier seasons from data/history, oldest first."""
    files = sorted(glob.glob(os.path.join(HISTORY, f"{league}_*.csv")))
    out = []
    for f in files:
        s = os.path.basename(f).split("_")[1].split(".")[0]
        if s < season:
            out.append(load_file(f, league, s))
    return out


def roll_history(season, sdir):
    """When a new season starts, keep last season's final data as history: football-data.co.uk files,
    and the European matches and club schedules the European model learns from."""
    y = int(season[:2])
    prev = f"{y - 1:02d}{y:02d}"
    for lg in DOMESTIC:
        dst = os.path.join(HISTORY, f"{lg}_{prev}.csv")
        src = os.path.join(DATA, "state", prev, f"fd_{lg}.csv")
        if not os.path.exists(dst) and os.path.exists(src):
            if lg == "mls":  # its 2026-27 window started in February 2026 (already in the 2025-26 file)
                copy_season_rows(src, dst, prev)
            else:
                shutil.copy(src, dst)
    pdir = os.path.join(DATA, "state", prev)
    dst = os.path.join(HISTORY, f"europe_{prev}.json")
    if europe is not None and not os.path.exists(dst) and os.path.exists(os.path.join(pdir, "espn_events_champions-league.json")):
        rows = []
        for lg in EUROPE:
            ev = jload(os.path.join(pdir, f"espn_events_{lg}.json"), {})
            summ = jload(os.path.join(pdir, f"espn_summaries_{lg}.json"), {})
            rows += europe.live_rows(lg, merge.europe_records(lg, list(ev.values()), summ, prev), ev)
        jsave(dst, rows)
        clubs = jload(os.path.join(pdir, "europe_clubs.json"), {}).get("games", {})
        jsave(os.path.join(HISTORY, f"europe_clubs_{prev}.json"), clubs)


def _month(d):
    return d.strftime("%Y%m")


def months_to_fetch(league, events, season, today):
    """ESPN scoreboard months to (re)load: the whole season so far on the first run, then the
    current window (4 days back to a month ahead) plus months holding unfinished past games."""
    if not events:
        d, end, out = season_start(season, league), today + timedelta(days=UPCOMING_DAYS), []
        while d <= end:
            if _month(d) not in out:
                out.append(_month(d))
            d += timedelta(days=27)
        if _month(end) not in out:
            out.append(_month(end))
        return out
    months = {_month(today - timedelta(days=4)), _month(today), _month(today + timedelta(days=UPCOMING_DAYS))}
    for e in events.values():
        d = date.fromisoformat(e["kickoff"][:10])
        if not e.get("completed") and today - timedelta(days=60) <= d < today:
            months.add(_month(d))
    return sorted(months)


_CHARS = str.maketrans({"ı": "i", "ø": "o", "Ø": "O", "ð": "d", "ł": "l", "Ł": "L", "æ": "ae", "ß": "ss", "đ": "d"})


def norm(name):
    s = unicodedata.normalize("NFKD", (name or "").translate(_CHARS)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("-", " ").replace(".", " ").split())


def find_player(name, squad):
    """Squad entry for a name written by another source (accents, initials, surname only)."""
    by_norm = {norm(n): p for n, p in squad.items()}
    k = norm(name)
    if k in by_norm:
        return by_norm[k]
    last = k.split()[-1:] if k else []
    cands = [p for n, p in by_norm.items() if last and n.split()[-1:] == last]
    if len(cands) == 1:
        return cands[0]
    first = k.split()[:1]
    cands = [p for n, p in by_norm.items() if first and len(k.split()) == 1 and n.split()[:1] == first]
    return cands[0] if len(cands) == 1 else None


NOT_OUT = ("doubtful", "back in training")


def injury_text(ret):
    low = (ret or "").strip().lower()
    if not low or low == "unknown":
        return "injured, return date unknown"
    if "season" in low:
        return "injured, out for the season"
    if low.startswith(("early", "mid", "late")):
        parts = ret.split()
        return f"injured, expected back {parts[0].lower()}-{parts[1]}" if len(parts) > 1 else f"injured, expected back {low}"
    return f"injured, {low}"


def team_news(fm_side, squad, overrides_entry, today):
    """Players out for this match. Returns (out, doubtful, known)."""
    out, doubtful, known = [], [], False
    if fm_side is not None:
        known = True
        for u in fm_side:
            p = find_player(u["name"], squad)
            rec = {"name": p["name"] if p else u["name"], "position": (p or {}).get("pos"),
                   "source": "FotMob"}
            ret = (u.get("expected_return") or "").strip()
            if u.get("type") == "suspension":
                rec["reason"] = "suspended"
            elif ret.lower() in NOT_OUT:
                rec["reason"] = f"injury, {ret.lower()}"
                doubtful.append(rec)
                continue
            else:
                rec["reason"] = injury_text(ret)
            out.append(rec)
    if overrides_entry and overrides_entry.get("checked") and \
            (today - date.fromisoformat(overrides_entry["checked"])).days <= 8:
        known = True
        have = {norm(x["name"]) for x in out}
        for x in overrides_entry.get("out", []):
            p = find_player(x["name"], squad)
            if norm((p or x)["name"]) not in have:
                out.append({"name": (p or x)["name"], "position": (p or {}).get("pos"),
                            "reason": x.get("reason") or "out", "source": x.get("source") or "manual"})
    return out, doubtful, known


def fotmob_ids(state_path, fixtures, league_of, now):
    """Links upcoming ESPN fixtures to FotMob matches (same day, closest team names)."""
    import difflib
    ids = jload(state_path, {})
    days = {}
    for e in fixtures:
        if e["espn_id"] not in ids:
            days.setdefault(e["kickoff"][:10].replace("-", ""), []).append(e)
    for d, evs in days.items():
        fm = sources.fotmob_day(d)
        if not fm:
            continue
        for e in evs:
            cands = [m for m in fm if m["league"] == league_of[e["espn_id"]]]
            def sc(m):
                return (difflib.SequenceMatcher(None, norm(m["home"]), norm(e["home"]["name"])).ratio()
                        + difflib.SequenceMatcher(None, norm(m["away"]), norm(e["away"]["name"])).ratio())
            if cands:
                best = max(cands, key=sc)
                if sc(best) >= 1.2:
                    ids[e["espn_id"]] = best["fotmob_id"]
    jsave(state_path, ids)
    return ids


def main():
    now = sources.now_utc()
    today = now.date()
    season = sources.season_code(now)
    sdir = os.path.join(DATA, "state", season)
    log = {"started": now.isoformat(), "season": season, "errors": [], "leagues": {}}
    roll_history(season, sdir)

    # ------------------------------------------------------------ 1. ESPN fixtures & results
    events, summaries = {}, {}
    for lg in LEAGUES:
        path = os.path.join(sdir, f"espn_events_{lg}.json")
        ev = jload(path, {})
        fetched = 0
        for mo in months_to_fetch(lg, ev, season, today):
            res = sources.espn_scoreboard(lg, mo)
            if res is None:
                continue
            if len(res) >= 500:
                log["errors"].append(f"{lg} {mo}: ESPN month query hit its limit, some games may be missing")
            fetched += 1
            for e in res:
                ev[e["espn_id"]] = e
        jsave(path, ev)
        events[lg] = ev
        # ------------------------------------------------------------ 2. match details
        spath = os.path.join(sdir, f"espn_summaries_{lg}.json")
        summ = jload(spath, {})
        new = 0
        for e in ev.values():
            if not e.get("completed") or e["espn_id"] in summ:
                continue
            ko = datetime.fromisoformat(e["kickoff"].replace("Z", "+00:00"))
            if now - ko < timedelta(hours=3):
                continue  # let ESPN's numbers settle
            s = sources.espn_summary(lg, e["espn_id"])
            if s:
                summ[e["espn_id"]] = s
                new += 1
        jsave(spath, summ)
        summaries[lg] = summ
        log["leagues"][lg] = {"scoreboard_months": fetched, "events": len(ev), "new_summaries": new}

    # ------------------------------------------------------------ 3. football-data.co.uk (FotMob for MLS)
    fd = {}
    for lg in DOMESTIC:
        path = os.path.join(sdir, f"fd_{lg}.csv")
        if LEAGUES[lg].get("stats") == "fotmob":
            # results and stats from FotMob in football-data.co.uk's format; each match's details fetched once
            cpath = os.path.join(sdir, f"fotmob_stats_{lg}.json")
            cache = jload(cpath, {})
            start = season_start(season, lg)
            seasons = [None] + sorted({str(start.year), str(today.year)})
            try:
                rows, new = fotmob_stats.season_rows(LEAGUES[lg]["fd_div"], LEAGUES[lg]["fotmob"], seasons, start,
                                                     today + timedelta(days=1), cache, log=log["errors"])
                jsave(cpath, cache)
                if rows:
                    with open(path, "w") as f:
                        f.write(fotmob_stats.to_csv(rows))
                log["leagues"][lg]["fotmob_new_stats"] = new
            except Exception as ex:  # FotMob down or changed: keep the last good copy
                log["errors"].append(f"FotMob stats {lg}: {ex!r}")
        else:
            text = sources.fd_results_csv(lg, season)
            if text and "HomeTeam" in text:
                with open(path, "w") as f:
                    f.write(text)
            elif os.path.exists(path):
                log["errors"].append(f"football-data.co.uk {lg}: download failed, using last good copy")
        fd[lg] = load_file(path, lg, season) if os.path.exists(path) else []
    fixtures_txt = sources.fd_fixtures_csv() or ""
    referees = {}
    if fixtures_txt:
        import csv
        import io
        for r in csv.DictReader(io.StringIO(fixtures_txt.lstrip("﻿"))):
            if r.get("Div") == "E0" and r.get("Referee"):
                d = datetime.strptime(r["Date"].strip(), "%d/%m/%Y").date()
                referees[(d.isoformat(), r["HomeTeam"].strip(), r["AwayTeam"].strip())] = r["Referee"].strip()

    # ------------------------------------------------------------ 4. teams
    tpath = os.path.join(sdir, "teams.json")
    team_map = jload(tpath, {})
    for lg in DOMESTIC:
        team_map[lg] = teams.learn(lg, fd[lg], list(events[lg].values()), team_map.get(lg))
        names = {m["home"] for m in fd[lg]} | {m["away"] for m in fd[lg]}
        missing = sorted(names - set(team_map[lg]))
        if missing:
            log["errors"].append(f"{lg}: no ESPN match for teams {missing}")
    jsave(tpath, team_map)
    espn_teams = {}
    for lg in LEAGUES:
        for e in events[lg].values():
            for side in ("home", "away"):
                t = e[side]
                if t.get("espn_id"):
                    espn_teams[t["espn_id"]] = {**espn_teams.get(t["espn_id"], {}), **{k: v for k, v in t.items() if v}}

    # ------------------------------------------------------------ 5. merge & cross-check
    matches, reports = {}, {}
    fd_of_espn = {}
    for lg in DOMESTIC:
        fe = teams.espn_to_fd(team_map[lg])
        fd_of_espn[lg] = fe
        matches[lg], reports[lg] = merge.merge_league(lg, season, fd[lg], list(events[lg].values()), summaries[lg], fe,
                                                      primary="FotMob" if LEAGUES[lg].get("stats") == "fotmob" else "football-data.co.uk")
        log["leagues"][lg]["cross_check"] = {k: v for k, v in reports[lg].items() if k != "conflicts"}
        log["leagues"][lg]["conflicts"] = reports[lg]["conflicts"][-30:]
    for lg in EUROPE:
        matches[lg] = merge.europe_records(lg, list(events[lg].values()), summaries[lg], season)

    # ------------------------------------------------------------ 6. players
    squad = {}
    for lg in LEAGUES:
        squad[lg] = players.season_players(matches[lg], summaries[lg], lambda m, side: m[side])

    # ------------------------------------------------------------ 7. estimates: one 60/40 recipe for every competition
    version = model_version()
    pdir = os.path.join(DATA, "predictions", season)
    overrides = jload(os.path.join(DATA, "overrides", "injuries.json"), {})
    analyst = jload(os.path.join(DATA, "overrides", "analyst.json"), {}).get("matches", {})
    upcoming = [e for lg in PREDICTED for e in events[lg].values()
                if e.get("status") == "pre" and now < datetime.fromisoformat(e["kickoff"].replace("Z", "+00:00")) < now + timedelta(days=4)]
    league_of = {e["espn_id"]: lg for lg in LEAGUES for e in events[lg].values()}
    fm_ids = fotmob_ids(os.path.join(sdir, "fotmob_ids.json"), upcoming, league_of, now)
    ref_path = os.path.join(sdir, "referees_live.json")
    live_refs = jload(ref_path, {})
    made = frozen = 0
    rec = None
    if engine is None:
        log["errors"].append(f"estimate engine unavailable: {_ENGINE_IMPORT_ERROR}")
    else:
        try:
            ref_rows = []
            for eid, r in live_refs.items():
                lg = league_of.get(eid)
                e = events.get(lg, {}).get(eid) if lg else None
                if e and e.get("completed"):
                    ref_rows.append({"league": lg, "kickoff": e["kickoff"], "home": e["home"]["name"], "away": e["away"]["name"],
                                     "hg": e.get("hg"), "ag": e.get("ag"), "referee": r["referee"]})
            rec = engine.build(season, now, fd, matches, events, team_map, sdir, log, jload, jsave, ref_rows)
        except Exception as ex:  # nothing new is published, frozen estimates stay as they are
            log["errors"].append(f"estimate engine: {ex!r}")
            traceback.print_exc()
    if rec:
        dom_of = {t["espn_id"]: (dl, n) for dl in DOMESTIC for n, t in (team_map.get(dl) or {}).items()}
        tables = {lg: engine.league_table([m for m in matches[lg]]) for lg in DOMESTIC}
        for lg in PREDICTED:
            made_lg = made
            fe = fd_of_espn.get(lg, {})
            for e in events[lg].values():
                path = os.path.join(pdir, lg, f"{e['espn_id']}.json")
                ko = datetime.fromisoformat(e["kickoff"].replace("Z", "+00:00"))
                if e.get("status") != "pre" or ko <= now:
                    frozen += os.path.exists(path)
                    continue  # kicked off (or postponed and not rescheduled): never rewritten
                if ko - now > timedelta(days=UPCOMING_DAYS):
                    continue
                if not e["home"].get("espn_id") or not e["away"].get("espn_id"):
                    continue  # knockout slot whose teams aren't known yet
                if lg in DOMESTIC:
                    hf, af = fe.get(e["home"]["espn_id"]), fe.get(e["away"]["espn_id"])
                    if not hf or not af:
                        log["errors"].append(f"{lg} {e['espn_id']}: unmapped team, no estimate")
                        continue
                else:
                    hf, af = e["home"]["espn_id"], e["away"]["espn_id"]
                news = None
                if ko - now < timedelta(days=4) and e["espn_id"] in fm_ids:
                    news = sources.fotmob_unavailable(fm_ids[e["espn_id"]])
                info, known = {}, True
                if news and news.get("referee"):
                    info["referee"] = news["referee"]
                    live_refs[e["espn_id"]] = {"referee": news["referee"], "league": lg}
                elif live_refs.get(e["espn_id"]):
                    info["referee"] = live_refs[e["espn_id"]]["referee"]
                for side, fk in (("home", hf), ("away", af)):
                    eid = e[side]["espn_id"]
                    if lg in DOMESTIC:
                        sq, team_key, comp_ms = squad[lg].get(fk, {}), fk, [m for m in matches[lg] if m["date"] < e["kickoff"][:10]]
                    else:
                        dl_n = dom_of.get(eid)
                        sq = squad[dl_n[0]].get(dl_n[1], {}) if dl_n else squad[lg].get(eid, {})
                        team_key, comp_ms = eid, matches[lg]
                    ov = (overrides.get("teams", {}).get(lg, {}) or {}).get(fk) if lg in DOMESTIC else None
                    out, doubtful, ok = team_news(news.get(side) if news else None, sq, ov, today)
                    if not ok:  # no team news yet: suspensions worked out from cards
                        own = squad[lg].get(team_key, {})
                        out = players.likely_suspended(lg, team_key, own, comp_ms) if own else []
                    known = known and ok
                    info[f"{side}_missing"] = engine.missing_info(out, sq, find_player)
                    info[f"{side}_doubtful"] = doubtful
                    if ko - now < timedelta(days=3):
                        last = sources.espn_team_last_match(eid, e["kickoff"])
                        if last:
                            lko = datetime.fromisoformat(last[0].replace("Z", "+00:00"))
                            info[f"{side}_rest_days"] = (ko.date() - lko.date()).days
                            info[f"{side}_europe_midweek"] = "UEFA" in (last[1] or "") and (ko - lko).days <= 4 and lg in DOMESTIC
                info["injuries_known"] = known
                info["derby"] = lg in DOMESTIC and is_derby(hf, af)
                info["stakes"] = ("Playoff match" if "playoff" in (e.get("season_slug") or "")
                                  else engine.stakes_now(lg, tables.get(lg, []), hf, af, e["kickoff"]))
                info["analyst_view"] = analyst.get(e["espn_id"])
                labels = {"home": e["home"]["name"], "away": e["away"]["name"]}
                try:
                    jsave(path, engine.make(rec, lg, e, hf, af, info, labels, now.isoformat(), version))
                    made += 1
                except Exception as ex:  # one bad fixture must not stop the run
                    log["errors"].append(f"estimate {lg} {e['espn_id']}: {ex!r}")
                    traceback.print_exc()
            log["leagues"][lg]["predictions"] = made - made_lg
        jsave(ref_path, live_refs)
    log["predictions"] = {"made_or_updated": made, "frozen_total": frozen}

    # ------------------------------------------------------------ 7b. model check for finished matches with no frozen estimate
    retro_path = os.path.join(DATA, "retro", f"{season}.json")
    retro_est = jload(retro_path, {})
    if rec:
        try:
            frozen_ids = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(pdir, "*", "*.json"))}
            done = []
            for lg in PREDICTED:
                for e in events[lg].values():
                    if e["kickoff"][:10] < season_window(season)[0].isoformat():
                        continue  # MLS: February-June 2026 games belong to last season's checks
                    if e.get("completed") and e["espn_id"] not in frozen_ids and e["home"].get("espn_id") and e["away"].get("espn_id"):
                        done.append({"id": e["espn_id"], "date": e["kickoff"][:10], "home_key": e["home"]["espn_id"],
                                     "away_key": e["away"]["espn_id"], "ctx": lg if lg in DOMESTIC else "europe"})

            def factory(wk):
                lf, jf = engine.fit(rec.all_matches, rec.groups, wk)
                from model.recipe import Recipe
                return Recipe(rec.params, rec.t).attach(rec.all_matches, wk, lf, jf, {})
            retro_est = engine.retro(factory, done, retro_est)
            jsave(retro_path, retro_est)
        except Exception as ex:
            log["errors"].append(f"model check: {ex!r}")
            traceback.print_exc()

    # ------------------------------------------------------------ 8. score frozen predictions
    by_id = {m.get("espn_id"): m for lg in LEAGUES for m in matches[lg] if m.get("espn_id")}
    scored = []
    for path in glob.glob(os.path.join(DATA, "predictions", "*", "*", "*.json")):
        p = jload(path, None)
        if not p:
            continue
        m = by_id.get(p["id"])
        ko = datetime.fromisoformat(p["kickoff"].replace("Z", "+00:00"))
        if m and ko <= now:
            res = predictions.score(p, m)
            if p.get("result") != res:
                p["result"] = res
                p["scored_at"] = now.isoformat()
                jsave(path, p)
        if p.get("result"):
            scored.append(p)
    log["scored"] = len(scored)

    # ------------------------------------------------------------ 9. site data
    log["calls"] = {"espn": sources.CALLS["espn"], "football_data": sources.CALLS["fd"], "fotmob": sources.CALLS["fotmob"]}
    log["team_news_linked"] = len(fm_ids)
    log["errors"] += sources.CALLS["errors"][-40:]
    log["finished"] = sources.now_utc().isoformat()
    site_data.write(ROOT, season, now, matches, events, summaries, fd, team_map, espn_teams, squad,
                    pdir, scored, log, reports, retro_est)
    jsave(os.path.join(DATA, "state", "last_run.json"), log)
    print(json.dumps({k: v for k, v in log.items() if k != "errors"}, indent=1))
    if log["errors"]:
        print("ERRORS:\n  " + "\n  ".join(log["errors"][:60]))


if __name__ == "__main__":
    main()
