import json
import os
import sys
from espn_api.nhl import League

# 1. Lue ympäristömuuttujat
league_id_env = os.environ.get("ESPN_LEAGUE_ID", "").strip()
espn_s2 = os.environ.get("ESPN_S2", "").strip()
swid = os.environ.get("SWID", "").strip()

if not league_id_env:
    print("VIRHE: ESPN_LEAGUE_ID puuttuu tai on tyhjä!")
    sys.exit(1)

LEAGUE_ID = int(league_id_env)
# Syyskuussa 2026 alkavalle kaudelle 2026-2027 ESPN käyttää vuotta 2027
YEAR = int(os.environ.get("ESPN_YEAR", 2027))

print(f"Yhdistetään liigaan ID: {LEAGUE_ID}, Kausi: {YEAR}...")
print(f"Autentikointi: espn_s2={'Kyllä' if espn_s2 else 'Ei'}, swid={'Kyllä' if swid else 'Ei'}")

try:
    # Syötetään espn_s2 ja swid VAIN jos ne oikeasti sisältävät arvon
    if espn_s2 and swid:
        league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=espn_s2, swid=swid)
    else:
        league = League(league_id=LEAGUE_ID, year=YEAR)
except Exception as e:
    print(f"\n[Etsintäapu] Yhdistäminen epäonnistui vuodella {YEAR}. Kokeillaan vuotta {YEAR-1}...")
    try:
        YEAR = YEAR - 1
        if espn_s2 and swid:
            league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=LEAGUE_ID, year=YEAR)
        print(f"Yhdistäminen onnistui vuodella {YEAR}!")
    except Exception as e2:
        print(f"Virhe epäonnistui myös vuodella {YEAR}: {e2}")
        raise e

# Kerätään joukkueiden tiedot
teams_data = []
for team in league.teams:
    teams_data.append({
        "id": team.team_id,
        "name": team.team_name,
        "abbrev": team.abbrev,
        "points_for": round(getattr(team, 'points_for', 0), 1),
        "wins": team.wins,
        "losses": team.losses,
        "ties": team.ties,
        "standing": team.standing
    })

# Kerätään vapaat agentit (TOP 30)
free_agents = league.free_agents(size=30)
fa_data = []
for player in free_agents:
    total_pts = getattr(player, 'total_points', 0)
    avg_pts = getattr(player, 'avg_points', 0)
    fa_data.append({
        "name": player.name,
        "position": player.position,
        "proTeam": player.proTeam,
        "total_points": round(total_pts, 1),
        "avg_points": round(avg_pts, 2),
        "injuryStatus": player.injuryStatus
    })

output = {
    "league_name": league.settings.name,
    "current_week": league.current_week,
    "teams": teams_data,
    "free_agents": fa_data
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu onnistuneesti!")
