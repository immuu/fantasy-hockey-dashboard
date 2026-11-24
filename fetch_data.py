import json
import os
import sys
from datetime import datetime, timezone
import espn_api.hockey.constant as c
from espn_api.hockey import League

# Load and clean environment variables
league_id_env = os.environ.get("ESPN_LEAGUE_ID", "1122471427").strip()
espn_s2 = os.environ.get("ESPN_S2", "").strip()
swid = os.environ.get("SWID", "").strip()

if not espn_s2 or not swid:
    print("VIRHE: ESPN_S2 tai SWID puuttuu! Aseta ne ympäristömuuttujina / GitHub-secreteinä.")
    sys.exit(1)

if not league_id_env:
    print("VIRHE: ESPN_LEAGUE_ID puuttuu tai on tyhjä!")
    sys.exit(1)

LEAGUE_ID = int(league_id_env)
YEAR = int(os.environ.get("ESPN_YEAR", 2027))

print(f"Yhdistetään liigaan ID: {LEAGUE_ID}...")

league = None
YEAR_USED = YEAR
for current_year in [YEAR, YEAR - 1]:
    try:
        print(f"Yritetään yhdistää kaudelle {current_year}...")
        if espn_s2 and swid:
            league = League(league_id=LEAGUE_ID, year=current_year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=LEAGUE_ID, year=current_year)
        YEAR_USED = current_year
        print(f"Yhdistäminen onnistui kaudelle {current_year}!")
        break
    except Exception as e:
        print(f"Kausi {current_year} epäonnistui: {e}")

if not league:
    print("VIRHE: Liigaan yhdistäminen epäonnistui kaikilla kausivuosilla.")
    sys.exit(1)

# Prepare scoring map
scoring_items = league.settings._raw_scoring_settings.get('scoringItems', [])
stat_points = {item['statId']: item['points'] for item in scoring_items}
name_to_stat_id = {v: int(k) for k, v in c.STATS_MAP.items()}

# ---- Daily points per team (this is a total-season-points league: no matchups) ----
# For every scoring period (day) we fetch the roster as it was that day and sum the
# daily applied points of players in active lineup slots (bench=7, IR=8 excluded).
# The sum over all days equals the official ESPN season total.
BENCH_SLOTS = (7, 8)
daily_points = {team.team_id: [] for team in league.teams}
last_period = getattr(league, 'scoringPeriodId', None) or getattr(league, 'current_week', 1)
for period in range(1, last_period + 1):
    try:
        raw = league.espn_request.league_get(params={'view': 'mRoster', 'scoringPeriodId': period})
    except Exception as e:
        print(f"Päivän {period} haku epäonnistui: {e}")
        for tid in daily_points:
            daily_points[tid].append(0.0)
        continue
    day_totals = {}
    for raw_team in raw.get('teams', []):
        s = 0.0
        for entry in raw_team.get('roster', {}).get('entries', []):
            if entry.get('lineupSlotId') in BENCH_SLOTS:
                continue
            for st in entry['playerPoolEntry']['player'].get('stats', []):
                if (st.get('statSplitTypeId') == 5 and st.get('scoringPeriodId') == period
                        and st.get('seasonId') == YEAR_USED):
                    s += st.get('appliedTotal', 0.0)
        day_totals[raw_team['id']] = round(s, 1)
    for tid in daily_points:
        daily_points[tid].append(day_totals.get(tid, 0.0))

def calculate_player_points(player):
    return round(getattr(player, 'total_points', 0.0), 1)

teams_data = []
for index, team in enumerate(league.teams, start=1):
    default_abbrev = team.team_name[:3].upper() if hasattr(team, 'team_name') and team.team_name else f"T{index}"
    abbrev = getattr(team, 'abbrev', default_abbrev)
    standing = getattr(team, 'standing', index)

    pos_counts = {"C": 0, "LW": 0, "RW": 0, "D": 0, "G": 0}
    roster_summary = []

    calc_team_points = 0.0
    for stat_name, val in team.stats.items():
        stat_id = name_to_stat_id.get(stat_name)
        pts_per_unit = stat_points.get(stat_id, 0.0) if stat_id else 0.0
        calc_team_points += val * pts_per_unit
    final_points = round(calc_team_points, 1)
    if daily_points.get(team.team_id):
        final_points = round(sum(daily_points[team.team_id]), 1)

    for player in getattr(team, 'roster', []):
        pos = getattr(player, 'position', 'N/A')
        p_name = getattr(player, 'name', 'Unknown')
        p_pts = calculate_player_points(player)
        if 'Center' in pos or pos == 'C':
            pos_key = 'C'
        elif 'Left' in pos or pos == 'LW':
            pos_key = 'LW'
        elif 'Right' in pos or pos == 'RW':
            pos_key = 'RW'
        elif 'Defense' in pos or pos == 'D':
            pos_key = 'D'
        elif 'Goalie' in pos or pos == 'G':
            pos_key = 'G'
        else:
            pos_key = None
        if pos_key:
            pos_counts[pos_key] += 1
        roster_summary.append({"name": p_name, "position": pos, "points": p_pts})

    team_daily = daily_points.get(team.team_id, [])
    cumulative = []
    sum_pts = 0
    for p in team_daily:
        sum_pts += p
        cumulative.append(round(sum_pts, 1))

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
        "top_players": sorted(roster_summary, key=lambda x: x['points'], reverse=True)[:5],
        "pointsHistory": cumulative,
        "weeklyScores": team_daily
    })

# Free agents (TOP 30)
free_agents = league.free_agents(size=30)
fa_data = []
for player in free_agents:
    calc_fa_pts = calculate_player_points(player)
    avg_pts = getattr(player, 'avg_points', 0)
    fa_data.append({
        "name": getattr(player, 'name', 'Tuntematon'),
        "position": getattr(player, 'position', 'N/A'),
        "proTeam": getattr(player, 'proTeam', 'N/A'),
        "total_points": calc_fa_pts,
        "avg_points": round(avg_pts, 2),
        "injuryStatus": getattr(player, 'injuryStatus', 'NORMAL')
    })

# Recent activity
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
            recent_activities.append({"date": act_date, "actions": actions_list})
except Exception as e:
    print(f"Aktiviteettien haku epäonnistui: {e}")

now_utc = datetime.now(timezone.utc)
last_updated_str = now_utc.strftime("%d.%m.%Y klo %H:%M UTC")

output = {
    "league_name": getattr(league.settings, 'name', 'ESPN Fantasy League'),
    "current_week": getattr(league, 'current_week', 1),
    "last_updated": last_updated_str,
    "teams": teams_data,
    "free_agents": fa_data,
    "recent_activity": recent_activities
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu ja tallennettu onnistuneesti!")
