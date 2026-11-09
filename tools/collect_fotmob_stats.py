"""Runs in GitHub Actions. Match stats from FotMob for a league football-data.co.uk has no stats for,
saved as football-data.co.uk-style CSVs, one per July-June season (data/history/<league>_<YYZZ>.csv).

  python tools/collect_fotmob_stats.py mls 130 USA 2022-07-01 2026-07-01 2022 2023 2024 2025 2026
      league key, FotMob league id, Div code, from, to (exclusive), FotMob seasons to read
"""
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import fotmob_stats as fs  # noqa: E402
from pipeline.sources import CALLS  # noqa: E402


def label(d):
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def main():
    league, fid, div, start, end, *seasons = sys.argv[1:]
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    os.makedirs("data/history", exist_ok=True)
    cache, log = {}, []
    rows, new = fs.season_rows(div, int(fid), seasons, start, end, cache, settle_hours=0, max_new=10000, log=log)
    by_season = defaultdict(list)
    for r in rows:
        by_season[label(fs.row_date(r))].append(r)
    for s, rs in sorted(by_season.items()):
        path = f"data/history/{league}_{s}.csv"
        with open(path, "w") as f:
            f.write(fs.to_csv(rs))
        full = sum(1 for r in rs if r.get("HC") is not None and r.get("HY") is not None and r.get("HS") is not None)
        refs = sum(1 for r in rs if r.get("Referee"))
        print(f"{path}: {len(rs)} matches, {full} with corners/cards/shots, {refs} with a referee")
    print("calls", {k: v for k, v in CALLS.items() if k != "errors"}, "errors", CALLS["errors"][:10], log)


if __name__ == "__main__":
    main()
