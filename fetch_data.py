import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HELSINKI_TZ = ZoneInfo("Europe/Helsinki")
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
# While doing so we also collect per-player daily records for the highlights/stats section.
from datetime import timedelta
BENCH_SLOTS = (7, 8)
POS_MAP = {1: 'C', 2: 'LW', 3: 'RW', 4: 'D', 5: 'G'}
team_names = {t.team_id: getattr(t, 'team_name', f"Team {t.team_id}") for t in league.teams}
daily_points = {team.team_id: [] for team in league.teams}
# records[(team_id, player_id)] = {"name", "pos", "days": {period: (points, active)}}
records = {}
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
            player = entry['playerPoolEntry']['player']
            active = entry.get('lineupSlotId') not in BENCH_SLOTS
            pts = 0.0
            stat_map = {}
            for st in player.get('stats', []):
                if (st.get('statSplitTypeId') == 5 and st.get('scoringPeriodId') == period
                        and st.get('seasonId') == YEAR_USED):
                    pts += st.get('appliedTotal', 0.0)
                    raw_stats = st.get('stats', {})
                    for sid, pval in st.get('appliedStats', {}).items():
                        if pval:
                            sname = c.STATS_MAP.get(str(sid), str(sid))
                            rval = raw_stats.get(str(sid), 0)
                            cur = stat_map.get(sname, [0.0, 0.0])
                            cur[0] += rval
                            cur[1] += pval
                            stat_map[sname] = cur
            if active:
                s += pts
            rec = records.setdefault((raw_team['id'], player['id']), {
                "name": player.get('fullName', 'Unknown'),
                "pos": POS_MAP.get(player.get('defaultPositionId'), '?'),
                "days": {},
                "stats": {}})
            rec["days"][period] = (round(pts, 1), active)
            if stat_map:
                order = {k: i for i, k in enumerate(
                    ['G', 'A', '+/-', 'PPG', 'PPA', 'SHG', 'SHA', 'GWG', 'HAT',
                     'SOG', 'HIT', 'BLK', 'FOW', 'FOL', 'PIM', 'W', 'OTL', 'SO', 'SV', 'GA']
                )}
                rec["stats"][period] = [
                    {
                        "s": k,
                        "v": int(round(v[0])) if abs(v[0] - round(v[0])) < 1e-6 else round(v[0], 1),
                        "p": round(v[1], 1)
                    }
                    for k, v in sorted(stat_map.items(), key=lambda kv: order.get(kv[0], 99))
                    if round(v[1], 1) != 0
                ]
        day_totals[raw_team['id']] = round(s, 1)
    for tid in daily_points:
        daily_points[tid].append(day_totals.get(tid, 0.0))


def build_highlights():
    """Compute fun / important stats from the retrospective daily data."""
    from statistics import mean, pstdev
    n_days = last_period
    # scoring period 1 .. last_period; the latest period is "today"
    today = datetime.now(HELSINKI_TZ).date()
    def date_of(p):
        return (today - timedelta(days=n_days - p)).isoformat()

    team_ids = list(daily_points.keys())
    hl = {"days": n_days, "first_date": date_of(1), "last_date": date_of(n_days)}

    # 1 & 2: best / worst team days
    all_days = [{"team": team_names[t], "day": i + 1, "date": date_of(i + 1), "points": p}
                for t in team_ids for i, p in enumerate(daily_points[t])]
    hl["best_days"] = sorted(all_days, key=lambda x: -x["points"])[:3]
    hl["worst_days"] = sorted(all_days, key=lambda x: x["points"])[:3]

    # 3: consistency
    cons = []
    for t in team_ids:
        pts = daily_points[t]
        cons.append({"team": team_names[t], "avg": round(mean(pts), 1), "std": round(pstdev(pts), 1),
                     "best": max(pts), "worst": min(pts),
                     "days_over_50": sum(1 for p in pts if p >= 50)})
    hl["consistency"] = sorted(cons, key=lambda x: x["std"])

    # 4: streaks relative to the team's own average
    streaks = []
    for t in team_ids:
        pts = daily_points[t]
        avg = mean(pts)
        best_up = best_down = cur_up = cur_down = 0
        for p in pts:
            if p > avg:
                cur_up += 1; cur_down = 0
            else:
                cur_down += 1; cur_up = 0
            best_up = max(best_up, cur_up); best_down = max(best_down, cur_down)
        cur_type = "up" if cur_up else "down"
        streaks.append({"team": team_names[t], "longest_hot": best_up, "longest_cold": best_down,
                        "current_type": cur_type, "current_len": cur_up or cur_down})
    hl["streaks"] = streaks

    # 5: player of the day hall of fame / shame (active lineup only)
    player_days = []
    for (tid, pid), rec in records.items():
        for p, (pts, active) in rec["days"].items():
            if active and pts != 0:
                player_days.append({"player": rec["name"], "pos": rec["pos"], "team": team_names[tid],
                                    "day": p, "date": date_of(p), "points": pts})
    hl["player_best_days"] = sorted(player_days, key=lambda x: -x["points"])[:5]
    hl["player_worst_days"] = sorted(player_days, key=lambda x: x["points"])[:5]

    # 6: MVP / bust per team (active points while on the team)
    mvp = []
    for t in team_ids:
        totals = []
        for (tid, pid), rec in records.items():
            if tid != t:
                continue
            tot = round(sum(pts for pts, act in rec["days"].values() if act), 1)
            days_active = sum(1 for pts, act in rec["days"].values() if act)
            totals.append({"player": rec["name"], "pos": rec["pos"], "points": tot, "days_active": days_active})
        if totals:
            totals.sort(key=lambda x: -x["points"])
            mvp.append({"team": team_names[t], "mvp": totals[0], "bust": totals[-1]})
    hl["mvp_bust"] = mvp

    # 7: bench regret (positive points scored by benched / IR players)
    regret = []
    for t in team_ids:
        total = 0.0
        worst = None
        for (tid, pid), rec in records.items():
            if tid != t:
                continue
            for p, (pts, act) in rec["days"].items():
                if not act and pts > 0:
                    total += pts
                    if worst is None or pts > worst["points"]:
                        worst = {"player": rec["name"], "day": p, "date": date_of(p), "points": pts}
        regret.append({"team": team_names[t], "points_on_bench": round(total, 1), "worst": worst})
    hl["bench_regret"] = sorted(regret, key=lambda x: -x["points_on_bench"])

    # 8: daily winners / last places
    wins = {t: 0 for t in team_ids}
    lasts = {t: 0 for t in team_ids}
    last_winner = None
    for i in range(n_days):
        day_scores = {t: daily_points[t][i] for t in team_ids}
        if len(set(day_scores.values())) == 1:
            continue
        w = max(day_scores, key=day_scores.get)
        l = min(day_scores, key=day_scores.get)
        wins[w] += 1; lasts[l] += 1
        last_winner = {"team": team_names[w], "day": i + 1, "date": date_of(i + 1), "points": day_scores[w]}
    hl["daily_wins"] = sorted(
        [{"team": team_names[t], "days_won": wins[t], "days_last": lasts[t]} for t in team_ids],
        key=lambda x: -x["days_won"])
    hl["latest_daily_winner"] = last_winner

    # 9: lead changes / gap timeline
    cum = {t: [] for t in team_ids}
    for t in team_ids:
        run = 0.0
        for p in daily_points[t]:
            run += p
            cum[t].append(round(run, 1))
    leaders, gaps, changes, prev = [], [], [], None
    biggest = {"gap": 0}
    for i in range(n_days):
        order = sorted(team_ids, key=lambda t: -cum[t][i])
        lead, last_t = order[0], order[-1]
        gap = round(cum[lead][i] - cum[last_t][i], 1)
        lead_over_second = round(cum[lead][i] - cum[order[1]][i], 1) if len(order) > 1 else 0
        gaps.append(gap)
        leaders.append(team_names[lead])
        if lead != prev:
            changes.append({"day": i + 1, "date": date_of(i + 1), "leader": team_names[lead]})
            prev = lead
        if lead_over_second > biggest["gap"]:
            biggest = {"gap": lead_over_second, "team": team_names[lead], "day": i + 1, "date": date_of(i + 1)}
    hl["lead_changes"] = changes
    hl["biggest_lead"] = biggest
    hl["gap_series"] = gaps
    hl["leader_series"] = leaders

    # 10: transactions retrospectively - first appearance after day 1 = pickup, disappearance = drop
    pickups, drops = [], []
    adds = {t: 0 for t in team_ids}
    drop_counts = {t: 0 for t in team_ids}
    by_player = {}
    for (tid, pid), rec in records.items():
        by_player.setdefault(pid, []).append((tid, rec))
    for (tid, pid), rec in records.items():
        days = sorted(rec["days"])
        first, last = days[0], days[-1]
        if first > 1:
            adds[tid] += 1
            pts = round(sum(pt for p, (pt, act) in rec["days"].items() if act), 1)
            pickups.append({"player": rec["name"], "pos": rec["pos"], "team": team_names[tid],
                            "day": first, "date": date_of(first), "points": pts})
        if last < n_days:
            drop_counts[tid] += 1
            # points scored by this player on OTHER teams after being dropped
            after = 0.0
            for otid, orec in by_player[pid]:
                if otid == tid:
                    continue
                after += sum(pt for p, (pt, act) in orec["days"].items() if p > last and act)
            own = round(sum(pt for p, (pt, act) in rec["days"].items() if act), 1)
            drops.append({"player": rec["name"], "pos": rec["pos"], "team": team_names[tid],
                          "day": last + 1, "date": date_of(last + 1), "points_after": round(after, 1),
                          "points_with_team": own})
    hl["best_pickups"] = sorted(pickups, key=lambda x: -x["points"])[:5]
    hl["worst_drops"] = sorted(drops, key=lambda x: -x["points_after"])[:5]
    hl["transactions"] = sorted(
        [{"team": team_names[t], "adds": adds[t], "drops": drop_counts[t]} for t in team_ids],
        key=lambda x: -x["adds"])
    return hl


highlights = build_highlights()

def build_recent_days(n=7):
    """Build detailed per-team, per-player breakdown for the last n scoring periods."""
    today = datetime.now(HELSINKI_TZ).date()
    start_p = max(1, last_period - n + 1)
    team_ids = list(daily_points.keys())
    days_out = []
    for p in range(start_p, last_period + 1):
        d_str = (today - timedelta(days=last_period - p)).isoformat()
        teams_list = []
        for tid in team_ids:
            t_pts = daily_points[tid][p - 1] if p - 1 < len(daily_points[tid]) else 0.0
            roster = []
            for (rtid, pid), rec in records.items():
                if rtid != tid or p not in rec["days"]:
                    continue
                pts, active = rec["days"][p]
                roster.append({
                    "player": rec["name"],
                    "pos": rec["pos"],
                    "points": pts,
                    "active": active,
                    "stats": rec.get("stats", {}).get(p, [])
                })
            roster.sort(key=lambda x: (not x["active"], -x["points"], x["player"]))
            teams_list.append({
                "team": team_names[tid],
                "points": t_pts,
                "roster": roster
            })
        teams_list.sort(key=lambda x: -x["points"])
        has_scores = any(t["points"] != 0 for t in teams_list) or any(
            pl["points"] != 0 for t in teams_list for pl in t["roster"]
        )
        days_out.append({
            "day": p,
            "date": d_str,
            "has_scores": has_scores,
            "teams": teams_list
        })
    return days_out


recent_days = build_recent_days(7)

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

now_fi = datetime.now(HELSINKI_TZ)
last_updated_str = now_fi.strftime("%d.%m.%Y klo %H:%M")

output = {
    "league_name": getattr(league.settings, 'name', 'ESPN Fantasy League'),
    "current_week": getattr(league, 'current_week', 1),
    "last_updated": last_updated_str,
    "teams": teams_data,
    "free_agents": fa_data,
    "recent_activity": recent_activities,
    "highlights": highlights,
    "recent_days": recent_days
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("data.json luotu ja tallennettu onnistuneesti!")
