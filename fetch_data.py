import json
import os
import sys
from espn_api.nhl import League

# 1. Lue ja siivoa ympäristömuuttujat
league_id_env = os.environ.get("ESPN_LEAGUE_ID", "").strip()
espn_s2 = os.environ.get("ESPN_S2", "").strip()
swid = os.environ.get("SWID", "").strip()

if not league_id_env:
    print("VIRHE: ESPN_LEAGUE_ID puuttuu tai on tyhjä!")
    sys.exit(1)

LEAGUE_ID = int(league_id_env)

# NHL-kaudelle 2026-2027 ESPN käyttää kausivuotta 2027 (tai 2026)
YEAR = int(os.environ.get("ESPN_YEAR", 2027))

print(f"Yhdistetään liigaan ID: {LEAGUE_ID}...")

league = None

for current_year in [YEAR, YEAR - 1]:
    try:
        print(f"Yritetään yhdistää kaudelle {current_year}...")
        if espn_s2 and swid:
            league = League(league_id=LEAGUE_ID, year=current_year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=LEAGUE_ID, year=current_year)
        
        print(f"Yhdistäminen onnistui kaudelle {current_year}!")
        break
    except Exception as e:
        print(f"Kausi {current_year} epäonnistui: {e}")

if not league:
    print("VIRHE: Liigaan yhdistäminen epäonnistui kaikilla kausivuosilla.")
    sys.exit(1)

# Kerätään joukkueiden tiedot turvallisesti
teams_data = []
for index, team in enumerate(league.teams, start=1):
    # Luodaan lyhenne joukkueen nimestä jos abbrev-kenttää ei ole (esim. "My Team" -> "MYT")
    default_abbrev = team.team_name[:3].upper() if hasattr(team, 'team_name') and team.team_name else f"T{index}"
    abbrev = getattr(team, 'abbrev', default_abbrev)
    
    standing = getattr(team, 'standing', index)

    teams_data.append({
        "id": team.team_id,
        "name": getattr(team, 'team_name', f"Team {team.team_id}"),
        "abbrev": abbrev,
        "points_for": round(getattr(team, 'points_for', 0), 1),
        "wins": getattr(team, 'wins', 0),
        "losses": getattr(team, 'losses', 0),
        "ties": getattr(team, 'ties', 0),
        "standing": standing
    })

# Kerätään vapaat agentit (TOP 30)
free_agents = league.free_agents(size=30)
fa_data = []
for player in free_agents:
    total_pts = getattr(player, 'total_points', 0)
    avg_pts = getattr(player, 'avg_points', 0)
    fa_data.append({
        "name": getattr(player, 'name', 'Tuntematon'),
        "position": getattr(player, 'position', 'N/A'),
        "proTeam": getattr(player, 'proTeam', 'N/A'),
        "total_points": round(total_pts, 1),
        "avg_points": round(avg_pts, 2),
        "injuryStatus": getattr(player, 'injuryStatus', 'NORMAL')
    })

output = {
    "league_name": getattr(league.settings, 'name', 'ESPN Fantasy League'),
    "current_week": getattr(league, 'current_week', 1),
    "teams": teams_data,
    "free_agents": fa_data
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu ja tallennettu onnistuneesti!")
