import json
import os
import sys
from espn_api.hockey import League

# 1. Lue ja siivoa ympäristömuuttujat
league_id_env = os.environ.get("ESPN_LEAGUE_ID", "").strip()
espn_s2 = os.environ.get("ESPN_S2", "").strip()
swid = os.environ.get("SWID", "").strip()

if not league_id_env:
    print("VIRHE: ESPN_LEAGUE_ID puuttuu tai on tyhjä!")
    sys.exit(1)

LEAGUE_ID = int(league_id_env)
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

def calculate_player_points(player_stats):
    """Laskee pelaajan todelliset fantasy-pisteet kaudelta/otteluista"""
    s = player_stats.get('total', {})
    if not s:
        return 0.0
    
    pts = 0.0
    # Kenttäpelaajien pisteet
    pts += s.get('G', 0) * 3.0
    pts += s.get('A', 0) * 2.0
    pts += s.get('+/-', 0) * 0.5
    pts += s.get('PIM', 0) * 0.2
    pts += s.get('PPG', 0) * 1.0
    pts += s.get('PPA', 0) * 0.5
    pts += s.get('SHG', 0) * 2.0
    pts += s.get('SHA', 0) * 1.0
    pts += s.get('GWG', 0) * 1.0
    pts += s.get('SOG', 0) * 0.2
    pts += s.get('HIT', 0) * 0.2
    pts += s.get('BLK', 0) * 0.5
    pts += s.get('HAT', 0) * 3.0
    
    # Maalivahtien pisteet
    pts += s.get('W', 0) * 4.0
    pts += s.get('L', 0) * -2.0
    pts += s.get('GA', 0) * -0.5
    pts += s.get('SV', 0) * 0.2
    pts += s.get('SO', 0) * 5.0
    
    return round(pts, 1)

# Kerätään joukkueiden tiedot, pisteet ja rosterit
teams_data = []
for index, team in enumerate(league.teams, start=1):
    default_abbrev = team.team_name[:3].upper() if hasattr(team, 'team_name') and team.team_name else f"T{index}"
    abbrev = getattr(team, 'abbrev', default_abbrev)
    standing = getattr(team, 'standing', index)

    pos_counts = {"C": 0, "LW": 0, "RW": 0, "D": 0, "G": 0}
    roster_summary = []
    calc_team_points = 0.0

    for player in getattr(team, 'roster', []):
        pos = getattr(player, 'position', 'N/A')
        p_name = getattr(player, 'name', 'Unknown')
        
        # Haetaan pelaajan 2027 kausitilastot
        stat_2027 = player.stats.get('Total 2027', {})
        p_pts = calculate_player_points(stat_2027)

        # Jos 2027-tilastoja ei vielä löydy, käytetään player.total_points-arvoa
        if p_pts == 0.0 and getattr(player, 'total_points', 0) > 0:
            p_pts = round(getattr(player, 'total_points', 0), 1)

        calc_team_points += p_pts

        if 'Center' in pos or pos == 'C': pos_key = 'C'
        elif 'Left' in pos or pos == 'LW': pos_key = 'LW'
        elif 'Right' in pos or pos == 'RW': pos_key = 'RW'
        elif 'Defense' in pos or pos == 'D': pos_key = 'D'
        elif 'Goalie' in pos or pos == 'G': pos_key = 'G'
        else: pos_key = None

        if pos_key:
            pos_counts[pos_key] += 1

        roster_summary.append({
            "name": p_name,
            "position": pos,
            "points": p_pts
        })

    # Käytetään ESPN:n virallista points_for-arvoa jos se on suurempi kuin nolla,
    # muussa tapauksessa käytetään laskettua reaaliaikaista summaa
    official_pf = round(getattr(team, 'points_for', 0), 1)
    final_points = official_pf if official_pf > 0 else round(calc_team_points, 1)

    teams_data.append({
        "id": team.team_id,
        "name": getattr(team, 'team_name', f"Team {team.team_id}"),
        "abbrev": abbrev,
        "points_for": final_points,
        "wins": getattr(team, 'wins', 0),
        "losses": getattr(team, 'losses', 0),
        "ties": getattr(team, 'ties', 0),
        "standing": standing,
        "positions": pos_counts,
        "top_players": sorted(roster_summary, key=lambda x: x['points'], reverse=True)[:5]
    })

# Kerätään vapaat agentit (TOP 30)
free_agents = league.free_agents(size=30)
fa_data = []
for player in free_agents:
    stat_2027 = player.stats.get('Total 2027', {})
    calc_fa_pts = calculate_player_points(stat_2027)
    if calc_fa_pts == 0.0 and getattr(player, 'total_points', 0) > 0:
        calc_fa_pts = round(getattr(player, 'total_points', 0), 1)

    avg_pts = getattr(player, 'avg_points', 0)

    fa_data.append({
        "name": getattr(player, 'name', 'Tuntematon'),
        "position": getattr(player, 'position', 'N/A'),
        "proTeam": getattr(player, 'proTeam', 'N/A'),
        "total_points": calc_fa_pts,
        "avg_points": round(avg_pts, 2),
        "injuryStatus": getattr(player, 'injuryStatus', 'NORMAL')
    })

# Kerätään viimeisimmät aktiviteetit
recent_activities = []
try:
    activities = league.recent_activity(size=25)
    for act in activities:
        act_date = getattr(act, 'date', None)
        actions_list = []
        for action in getattr(act, 'actions', []):
            team_obj, action_type, player_obj = action[0], action[1], action[2]
            team_name = getattr(team_obj, 'team_name', str(team_obj))
            player_name = getattr(player_obj, 'name', str(player_obj))
            actions_list.append({
                "team": team_name,
                "action": action_type,
                "player": player_name
            })
        if actions_list:
            recent_activities.append({
                "date": act_date,
                "actions": actions_list
            })
except Exception as e:
    print(f"Aktiviteettien haku epäonnistui: {e}")

output = {
    "league_name": getattr(league.settings, 'name', 'ESPN Fantasy League'),
    "current_week": getattr(league, 'current_week', 1),
    "teams": teams_data,
    "free_agents": fa_data,
    "recent_activity": recent_activities
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu ja tallennettu onnistuneesti!")
