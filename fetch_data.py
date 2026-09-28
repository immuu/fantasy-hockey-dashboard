import json
import os
from espn_api.nhl import League

# Hae asetukset ympäristömuuttujista (tai käytä oletuksia)
LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", 12345678))  # Aseta oma ID
YEAR = 2026
ESPN_S2 = os.environ.get("ESPN_S2", "")
SWID = os.environ.get("SWID", "")

print(f"Yhdistetään liigaan ID: {LEAGUE_ID}...")

if ESPN_S2 and SWID:
    league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=ESPN_S2, swid=SWID)
else:
    league = League(league_id=LEAGUE_ID, year=YEAR)

# Kerätään sarjataulukko ja joukkueiden tiedot
teams_data = []
for team in league.teams:
    teams_data.append({
        "id": team.team_id,
        "name": team.team_name,
        "abbrev": team.abbrev,
        "points_for": round(team.points_for, 1),
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

# Tallennettaan JSON-tiedostoon
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu onnistuneesti!")
