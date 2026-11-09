"""Step 2 adjustments. Each returns a list of Adjustment records; none are mixed silently.

Sizes marked PROVISIONAL are not yet calibrated on data and are labelled as such
on the site. Sizes marked MEASURED were estimated from past seasons (see backtest).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

MOMENTUM_CAP = 0.10
TEAM_CAP = 0.25


@dataclass
class Adjustment:
    kind: str          # momentum | absences | referee | congestion | derby
    stat: str          # goals | cards | ...
    side: str          # home | away | both
    factor: float      # multiplier applied to the expected value
    detail: str
    status: str        # measured | provisional | info (shown, not applied)

    def to_dict(self):
        d = asdict(self)
        d["effect_pct"] = round((self.factor - 1) * 100, 1)
        return d


def _points(m, team):
    hg, ag = m["hg"], m["ag"]
    if m["home"] == team:
        return 3 if hg > ag else 1 if hg == ag else 0
    return 3 if ag > hg else 1 if hg == ag else 0


def momentum(cur, team, side, coef):
    games = sorted([m for m in cur if team in (m["home"], m["away"]) and m.get("hg") is not None],
                   key=lambda m: m["date"])
    if len(games) < 6:
        return []
    ppg_all = sum(_points(m, team) for m in games) / len(games)
    last = games[-5:]
    ppg5 = sum(_points(m, team) for m in last) / 5
    eff = max(-MOMENTUM_CAP, min(MOMENTUM_CAP, coef * (ppg5 - ppg_all)))
    detail = f"{ppg5:.1f} pts/game in last 5 vs {ppg_all:.1f} season average"
    if coef == 0:
        return [Adjustment("momentum", "goals", side, 1.0,
                           detail, "info")]
    return [Adjustment("momentum", "goals", side, 1 + eff, detail, "measured")]


def referee(ref_name, ref_matches, league_cards_per_match, k=10.0):
    """ref_matches: past matches of this referee with card counts (any season)."""
    if not ref_name:
        return [Adjustment("referee", "cards", "both", 1.0, "Referee not announced yet", "info")]
    games = [m for m in ref_matches if m.get("hcards") is not None and m.get("acards") is not None]
    n = len(games)
    if n == 0:
        return [Adjustment("referee", "cards", "both", 1.0, f"{ref_name}: no past matches on record", "info")]
    total = sum(m["hcards"] + m["acards"] for m in games)
    mu = league_cards_per_match
    detail = f"{ref_name}: {total / n:.1f} cards per game in {n} games (league {mu:.1f})"
    if k >= 1e8:
        return [Adjustment("referee", "cards", "both", 1.0,
                           detail, "info")]
    factor = (total + k * mu) / ((n + k) * mu)
    return [Adjustment("referee", "cards", "both", factor, detail, "measured")]


def congestion(rest_days, european_midweek, side, team):
    out = []
    if rest_days is not None and rest_days < 4:
        out.append(Adjustment("congestion", "goals", side, 0.97,
                              f"{team}: {rest_days} days' rest", "provisional"))
    elif european_midweek:
        out.append(Adjustment("congestion", "goals", side, 0.98,
                              f"{team}: played in Europe midweek", "provisional"))
    return out


DERBIES = [
    # Premier League
    ("Arsenal", "Tottenham"), ("Man City", "Man United"), ("Liverpool", "Everton"),
    ("Arsenal", "Chelsea"), ("Chelsea", "Tottenham"), ("Liverpool", "Man United"),
    ("Newcastle", "Sunderland"), ("West Ham", "Tottenham"), ("Crystal Palace", "Brighton"),
    # La Liga
    ("Real Madrid", "Barcelona"), ("Real Madrid", "Ath Madrid"), ("Barcelona", "Espanol"),
    ("Sevilla", "Betis"), ("Ath Bilbao", "Sociedad"), ("Valencia", "Levante"),
    ("Getafe", "Leganes"), ("Ath Madrid", "Barcelona"), ("Real Madrid", "Getafe"),
    # Serie A
    ("Inter", "Milan"), ("Roma", "Lazio"), ("Juventus", "Torino"), ("Juventus", "Inter"), ("Genoa", "Sampdoria"),
    ("Juventus", "Milan"), ("Napoli", "Roma"), ("Fiorentina", "Juventus"),
    # Bundesliga
    ("Dortmund", "Schalke 04"), ("Bayern Munich", "Dortmund"), ("Hamburg", "Werder Bremen"), ("FC Koln", "M'gladbach"),
    ("Union Berlin", "Hertha"), ("Hamburg", "St Pauli"), ("Stuttgart", "Karlsruhe"),
    # Ligue 1
    ("Paris SG", "Marseille"), ("Lyon", "St Etienne"), ("Lens", "Lille"), ("Nice", "Monaco"), ("Marseille", "Lyon"),
    ("Paris SG", "Paris FC"), ("Rennes", "Nantes"),
    # Eredivisie
    ("Ajax", "Feyenoord"), ("Ajax", "PSV Eindhoven"), ("Feyenoord", "PSV Eindhoven"), ("Feyenoord", "Sparta Rotterdam"),
    ("Feyenoord", "Excelsior"), ("Groningen", "Heerenveen"), ("Twente", "Heracles"),
    # Primeira Liga
    ("Benfica", "Sp Lisbon"), ("Benfica", "Porto"), ("Porto", "Sp Lisbon"), ("Sp Braga", "Guimaraes"), ("Porto", "Boavista"),
    # Super Lig
    ("Galatasaray", "Fenerbahce"), ("Galatasaray", "Besiktas"), ("Fenerbahce", "Besiktas"), ("Trabzonspor", "Fenerbahce"),
    ("Trabzonspor", "Galatasaray"), ("Trabzonspor", "Besiktas"), ("Ankaragucu", "Genclerbirligi"),
    # Segunda Division
    ("Sp Gijon", "Oviedo"), ("Zaragoza", "Huesca"), ("Las Palmas", "Tenerife"), ("Malaga", "Granada"), ("Almeria", "Granada"),
    ("Malaga", "Cordoba"), ("Valladolid", "Burgos"), ("Valladolid", "Cultural Leonesa"), ("Leganes", "Alcorcon"),
    ("Santander", "Sp Gijon"),
    # MLS (FotMob names): El Trafico, Cascadia, Hudson River, Hell is Real, Texas, Canadian Classique, Florida,
    # California Clasico, Rocky Mountain Cup, Atlantic Cup, SoCal
    ("Los Angeles FC", "LA Galaxy"), ("Seattle Sounders FC", "Portland Timbers"), ("Seattle Sounders FC", "Vancouver Whitecaps"),
    ("Portland Timbers", "Vancouver Whitecaps"), ("New York City FC", "Red Bull New York"), ("Columbus Crew", "FC Cincinnati"),
    ("Houston Dynamo FC", "FC Dallas"), ("Austin FC", "FC Dallas"), ("Austin FC", "Houston Dynamo FC"), ("Toronto FC", "CF Montréal"),
    ("Orlando City", "Inter Miami CF"), ("LA Galaxy", "San Jose Earthquakes"), ("Real Salt Lake", "Colorado Rapids"),
    ("DC United", "Red Bull New York"), ("San Diego FC", "Los Angeles FC"), ("San Diego FC", "LA Galaxy"),
]
_DERBY_SET = {frozenset(p) for p in DERBIES}


def is_derby(home, away):
    return frozenset((home, away)) in _DERBY_SET


def derby(home, away, factor):
    if is_derby(home, away):
        return [Adjustment("derby", "cards", "both", factor, "Derby / rivalry match", "measured")]
    return []


ABSENCE_FACTOR = 0.4   # share of a player's contribution that is NOT replaced (PROVISIONAL)
DEFENSIVE_BUMP = 0.03  # per missing regular goalkeeper/defender, to opponent goals (PROVISIONAL)


def absences(team, side, opp_side, missing, squad_contrib):
    """missing: [{name, reason, position}]; squad_contrib: {name: {goals, assists, starts, games}}"""
    out = []
    total = sum(p["goals"] + 0.5 * p["assists"] for p in squad_contrib.values()) or 1.0
    team_games = max((p.get("games") or p.get("apps", 0) for p in squad_contrib.values()), default=0) or 1
    for p in missing:
        c = squad_contrib.get(p["name"])
        if not c:
            continue
        share = (c["goals"] + 0.5 * c["assists"]) / total
        if share > 0:
            out.append(Adjustment("absences", "goals", side, 1 - share * ABSENCE_FACTOR,
                                  f"{p['name']} out ({p.get('reason', 'unavailable')}): "
                                  f"{c['goals']}G {c['assists']}A, {share:.0%} of team goal involvement",
                                  "provisional"))
        regular = c.get("starts", 0) >= 0.6 * team_games
        if regular and p.get("position") in ("G", "D"):
            out.append(Adjustment("absences", "goals", opp_side, 1 + DEFENSIVE_BUMP,
                                  f"{p['name']} ({'goalkeeper' if p['position'] == 'G' else 'defender'}, regular starter) out",
                                  "provisional"))
    return out


def apply(base, adjustments):
    """base: {stat: [home, away]}. Returns adjusted copy with a ±25% cap per team per stat."""
    mult = {stat: [1.0, 1.0] for stat in base}
    for a in adjustments:
        if a.status == "info" or a.stat not in mult:
            continue
        idx = [0, 1] if a.side == "both" else [0] if a.side == "home" else [1]
        for i in idx:
            mult[a.stat][i] *= a.factor
    out = {}
    for stat, (h, aw) in base.items():
        mh = max(1 - TEAM_CAP, min(1 + TEAM_CAP, mult[stat][0]))
        ma = max(1 - TEAM_CAP, min(1 + TEAM_CAP, mult[stat][1]))
        out[stat] = [h * mh, aw * ma]
    return out, mult
