"""
Fantasy Usage Stats - the website
Run with:  python3 -m streamlit run app.py
"""

import pandas as pd
import streamlit as st
import phase1
import news
import leagues
import rankings
import projections

st.set_page_config(page_title="Fantasy Usage Stats", layout="wide")
st.title("Fantasy Usage Stats")
st.caption(f"Regular season · Data: nflverse · Player photos: NFL · "
           "Charting data (first reads, drops, contested and catchable balls): FTN Data via nflverse")


# ---------- Part 0: latest NFL news at the top ----------
@st.cache_data(ttl=60 * 10)  # check for new news every 10 minutes
def get_news(source):
    return news.get_headlines(source)


def show_news(source, show_times):
    """One news column. ESPN stamps every item with the feed's update time,
    so per-item times are only shown for feeds that have real ones."""
    headlines = get_news(source)
    if not headlines:
        st.write(f"{source} news is unavailable right now.")
        return
    times = [h["published"] for h in headlines if h["published"]]
    if times and not show_times:
        st.caption(f"Updated {max(times).strftime('%b %d, %-I:%M %p')} ET")
    def show_item(h):
        line = f"**[{h['title']}]({h['link']})**"
        if show_times and h["published"]:
            line += f"  \n{h['published'].strftime('%b %d, %-I:%M %p')} ET"
        st.markdown(line)

    for h in headlines[:8]:
        show_item(h)
    # A toggle, not an expander: Streamlit doesn't allow an expander inside another one
    if len(headlines) > 8 and st.toggle(f"Show more ({len(headlines) - 8})", key=f"more_{source}"):
        for h in headlines[8:]:
            show_item(h)


with st.expander("Latest NFL news", expanded=True):
    rotowire_tab, rumors_tab, espn_tab = st.tabs(
        ["Player news (RotoWire)", "Injuries & transactions (Pro Football Rumors)", "Headlines (ESPN)"])
    with rotowire_tab:
        show_news("RotoWire", show_times=True)
    with rumors_tab:
        show_news("Pro Football Rumors", show_times=True)
    with espn_tab:
        show_news("ESPN", show_times=False)
    st.link_button("Breaking updates: Underdog NFL on X", "https://x.com/UnderdogNFL")


# ---------- Part 1: load the data once a day, then reuse it ----------
# max_entries=1: keep only one season in memory at a time, so the free server doesn't run out
@st.cache_data(ttl=60 * 60 * 24, max_entries=1)  # refresh once a day
def get_data(season, data_version):
    players = phase1.load_players()
    plays = phase1.load_plays(season)
    snaps = phase1.load_snaps(players, season)
    weekly = phase1.build_weekly(plays, players, snaps)
    status = phase1.load_status(season)
    schedule = phase1.load_schedule(season)
    return plays, players, snaps, weekly, status, schedule


st.sidebar.header("Filters")
season = st.sidebar.selectbox("Season", phase1.SEASONS)
with st.spinner(f"Loading {season} NFL data (about 30 seconds the first time)..."):
    plays, players, snaps, weekly, status, schedule = get_data(season, phase1.DATA_VERSION)
# Keep the full season for projections, before the week filter trims it
plays_all, snaps_all, weekly_all = plays, snaps, weekly


# ---------- Part 2: filters in the sidebar (they apply to every tab) ----------
first, last = int(plays["week"].min()), int(plays["week"].max())
weeks = st.sidebar.slider("Weeks", first, last, (first, last))
plays = plays[plays["week"].between(weeks[0], weeks[1])]
snaps = snaps[snaps["week"].between(weeks[0], weeks[1])]
weekly = weekly[weekly["week"].between(weeks[0], weeks[1])]
table = phase1.build_table(plays, players, snaps)
table = table.merge(status, on="player_id", how="left")
table["status"] = table["status"].fillna("Unknown")
table.loc[table["status"] == "Injured reserve", "status"] = "⚠️ Injured reserve"


def load_out_for_season(path="out_for_season.txt"):
    """Names from out_for_season.txt (one per line, # lines ignored)."""
    try:
        with open(path) as f:
            return {line.strip() for line in f if line.strip() and not line.startswith("#")}
    except FileNotFoundError:
        return set()


out_for_season = load_out_for_season() if season == phase1.SEASON else set()
table.loc[table["full_name"].isin(out_for_season), "status"] = "❌ Out for season"

# Scoring: pick a preset, then change any value under "Customize scoring"
PRESETS = {"PPR": 1.0, "Half PPR": 0.5, "Standard": 0.0}   # points per catch
scoring = st.sidebar.radio("Scoring format", list(PRESETS), horizontal=True)
LABELS = {
    "catches": "Per catch", "receiving_yards": "Per receiving yard",
    "rushing_yards": "Per rushing yard", "passing_yards": "Per passing yard",
    "passing_tds": "Passing TD", "rush_rec_tds": "Rushing/receiving TD",
    "interceptions": "Interception thrown", "fumbles_lost": "Fumble lost",
    "two_point_conversions": "Two-point conversion",
}
settings = dict(phase1.PPR_SCORING, catches=PRESETS[scoring])
with st.sidebar.expander("Customize scoring"):
    for stat, label in LABELS.items():
        # The key includes the preset, so switching presets resets these boxes
        settings[stat] = st.number_input(label, value=settings[stat], step=0.5 if
                                         abs(settings[stat]) >= 1 else 0.01,
                                         key=f"{scoring}_{stat}")
if settings != dict(phase1.PPR_SCORING, catches=PRESETS[scoring]):
    scoring = "Custom"

table["fantasy_points"] = phase1.score(table, settings)
weekly = weekly.assign(fantasy_points=phase1.score(weekly, settings))


# ---------- Projections: next week and rest of season ----------
def load_shadows(path="shadow_matchups.txt"):
    """{receiver: cornerback} from shadow_matchups.txt."""
    try:
        with open(path) as f:
            pairs = [line.split(",", 1) for line in f
                     if line.strip() and not line.startswith("#") and "," in line]
        return {receiver.strip(): corner.strip() for receiver, corner in pairs}
    except FileNotFoundError:
        return {}


@st.cache_data(ttl=60 * 60)  # injury reports change during the week: check every hour
def get_injury_report(season, week):
    return phase1.load_injury_report(season, week)


next_week = int(plays_all["week"].max()) + 1
has_projections = next_week <= 18
if has_projections:
    weekly_all = weekly_all.assign(fantasy_points=phase1.score(weekly_all, settings))
    full_table = phase1.build_table(plays_all, players, snaps_all)
    full_table["fantasy_points"] = phase1.score(full_table, settings)
    week_proj = projections.project(weekly_all, full_table, schedule, plays_all,
                                    "fantasy_points", next_week, load_shadows())
    ros = projections.rest_of_season(weekly_all, full_table, schedule, plays_all,
                                     "fantasy_points", next_week)
    week_proj = week_proj.merge(ros, on="player_id", how="left")

    # Who can't play this week: official injury report (Out / Doubtful), the hand-kept
    # out_this_week.txt list, and anyone not on the active roster
    out_this_week = load_out_for_season("out_this_week.txt")
    report = get_injury_report(season, next_week)
    week_proj["injury"] = week_proj["player_id"].map(report).fillna("")
    week_proj.loc[week_proj["full_name"].isin(out_this_week), "injury"] = "Out"
    week_proj = week_proj.merge(status[["player_id", "status"]], on="player_id", how="left")
    cannot_play = (week_proj["injury"].isin(["Out", "Doubtful"]) |
                   (week_proj["status"] != "Active") |
                   week_proj["full_name"].isin(out_for_season))
    week_proj.loc[cannot_play, "projection"] = 0.0
    week_proj.loc[week_proj["full_name"].isin(out_for_season), "ros_points"] = 0.0
    week_proj["injury"] = week_proj["injury"].replace(
        {"Out": "🚫 Out", "Doubtful": "🚫 Doubtful", "Questionable": "❓ Questionable"})
    week_proj = week_proj.drop(columns="status")

table = phase1.add_expected_points(table, "fantasy_points")

team = st.sidebar.selectbox("Team", ["All"] + sorted(table["team"].unique()))
if team != "All":
    table = table[table["team"] == team]


# ---------- Part 3: how columns are named and formatted ----------
COLUMN_NAMES = {
    "player": "Player", "team": "Team", "position": "Pos", "status": "Status",
    "snap_share": "Snap share %", "targets": "Targets", "target_share": "Target share %",
    "first_read_share": "First-read share %", "air_yards_share": "Air yards share %",
    "adot": "aDOT", "rz_target_share": "RZ target share %",
    "catchable_targets": "Catchable", "contested_targets": "Contested", "drops": "Drops",
    "carries": "Carries", "rush_share": "Rush share %", "goal_line_carries": "GL carries",
    "passing_yards": "Pass yds", "passing_tds": "Pass TD", "interceptions": "INT",
    "rushing_yards": "Rush yds", "rush_rec_tds": "Rush/rec TD",
    "fantasy_points": f"{scoring} points", "fantasy_team": "Fantasy team", "expected_points": "Expected points",
    "points_below_expected": "Points below expected",
    "games": "Games", "fg_made": "FG made", "fg_attempts": "FG att", "fg_pct": "FG %",
    "fg_0_39": "FG 0-39", "fg_40_49": "FG 40-49", "fg_50_plus": "FG 50+",
    "fg_50_attempts": "FG 50+ att", "longest_fg": "Long", "xp_made": "XP made",
    "xp_attempts": "XP att", "k_points": "Fantasy points", "points_per_game": "Points per game",
    "sacks": "Sacks", "sack_rate": "Sack rate %", "fumbles_recovered": "Fumbles rec",
    "takeaways": "Takeaways", "defensive_tds": "D/ST TD", "safeties": "Safeties",
    "points_allowed_per_game": "Points allowed/game", "yards_allowed_per_game": "Yards allowed/game",
    "dst_points": "Fantasy points",
    "opponent": "Opp", "matchup_label": "Matchup", "implied": "Team implied pts",
    "shadow": "Shadowed by", "injury": "Injury",
    "snap_share_earlier": "Snap % before", "snap_share_recent": "Snap % recent",
    "target_share_earlier": "Target % before", "target_share_recent": "Target % recent",
    "carries_earlier": "Carries/g before", "carries_recent": "Carries/g recent",
    "points_earlier": "Pts/g before", "points_recent": "Pts/g recent",
    "trend": "Usage change (exp. pts/g)", "projection": "Projected pts", "ros_points": "Rest of season pts",
}
PERCENT_COLUMNS = ["snap_share_earlier", "snap_share_recent", "target_share_earlier",
                   "target_share_recent", "fg_pct", "sack_rate", "snap_share", "target_share", "first_read_share", "air_yards_share",
                   "rz_target_share", "rush_share"]
COUNT_COLUMNS = ["games", "fg_made", "fg_attempts", "fg_0_39", "fg_40_49", "fg_50_plus",
                 "fg_50_attempts", "xp_made", "xp_attempts", "sacks", "fumbles_recovered",
                 "takeaways", "defensive_tds", "safeties", "passing_yards", "passing_tds", "interceptions", "rushing_yards",
                 "rush_rec_tds", "targets", "catchable_targets", "contested_targets", "drops",
                 "carries", "goal_line_carries"]


def show_table(rows, columns):
    """Show the chosen columns with nice names, percentages, and rounding."""
    shown = rows[columns].copy()
    for col in columns:
        if col in PERCENT_COLUMNS:
            shown[col] = shown[col] * 100
        if col in COUNT_COLUMNS:
            shown[col] = shown[col].astype(int)
    shown = shown.round(1).rename(columns=COLUMN_NAMES)
    st.dataframe(shown, hide_index=True)


# ---------- Part 4: the three tabs ----------
(proj_tab, trend_tab, qbs_tab, receivers_tab, rbs_tab, k_tab, dst_tab, buy_low_tab, league_tab,
 player_tab) = st.tabs(["Projections", "Trending", "Quarterbacks", "Receivers", "Running backs",
                        "Kickers", "Defenses", "Buy low", "My league", "Player search"])

with trend_tab:
    if not has_projections:
        st.info("Pick the current season in the sidebar to see who's trending.")
    else:
        recent_games = st.select_slider("Compare the last ___ games with earlier games",
                                        options=[1, 2, 3, 4], value=2)
        st.caption("Players are ranked by the change in expected points per game (their usage: "
                   "targets, air yards, red zone looks, carries), because a bigger role usually "
                   "shows up before the points do. **1 game** catches sudden role changes but can "
                   "be fooled by one-off games; **3-4 games** is steadier. Needs at least 3 "
                   "earlier games.")
        # Trending: last N games vs. earlier games (receivers and running backs)
        trending = projections.trends(weekly_all[weekly_all["position"] != "QB"], full_table,
                                      "fantasy_points", recent_games=recent_games)
        trending = trending.merge(status[["player_id", "status"]], on="player_id", how="left")
        trend_pos = st.radio("Position", ["All", "RB", "WR", "TE"], horizontal=True,
                             key="trend_pos")
        rows = trending[trending["status"] == "Active"]
        if trend_pos != "All":
            rows = rows[rows["position"] == trend_pos]
        if team != "All":
            rows = rows[rows["team"] == team]
        columns = ["player", "team", "position", "snap_share_earlier", "snap_share_recent",
                   "target_share_earlier", "target_share_recent", "carries_earlier",
                   "carries_recent", "points_earlier", "points_recent", "trend"]
        st.subheader("📈 Trending up")
        show_table(rows.sort_values("trend", ascending=False).head(15), columns)
        st.subheader("📉 Trending down")
        show_table(rows.sort_values("trend").head(15), columns)

with proj_tab:
    if not has_projections:
        st.info("This season is over. Pick the current season in the sidebar to see projections.")
    else:
        st.write(f"**Week {next_week} projections** ({scoring} scoring)")
        st.caption("Projection = recent and season form (half points, half usage) × matchup "
                   "(points the opponent allows to the position) × Vegas implied team points "
                   "× shadow coverage, pulled toward average to account for luck. Backtested on "
                   "weeks 5-10: average miss 5.8 points per player with no overall bias, better "
                   "than a season average. Treat these as estimates.")
        proj_rows = week_proj.merge(status[["player_id", "status"]], on="player_id", how="left")
        proj_rows["status"] = proj_rows["status"].fillna("Unknown")
        proj_rows.loc[proj_rows["status"] == "Injured reserve", "status"] = "⚠️ Injured reserve"
        proj_rows.loc[proj_rows["full_name"].isin(out_for_season), "status"] = "❌ Out for season"
        proj_rows["matchup_label"] = pd.cut(proj_rows["matchup"], [0, 0.95, 1.05, 2],
                                            labels=["🔴 Tough", "⚪ Neutral", "🟢 Good"])
        proj_rows["shadow"] = proj_rows["shadow"].where(proj_rows["shadow"] == "",
                                                        "🛡️ " + proj_rows["shadow"])
        proj_pos = st.radio("Position", ["All", "QB", "RB", "WR", "TE"], horizontal=True,
                            key="proj_pos")
        if proj_pos != "All":
            proj_rows = proj_rows[proj_rows["position"] == proj_pos]
        if team != "All":
            proj_rows = proj_rows[proj_rows["team"] == team]
        proj_rows = proj_rows[proj_rows["baseline"] >= 3].sort_values("projection",
                                                                      ascending=False)
        show_table(proj_rows, ["player", "team", "position", "status", "injury", "opponent",
                               "matchup_label", "implied", "shadow", "projection",
                               "ros_points"])
        st.caption("Injury designations come from the official NFL injury report (released "
                   "Wednesday to Friday) plus out_this_week.txt for news that breaks earlier. "
                   "Out and Doubtful players project to 0. Shadow coverage comes from "
                   "shadow_matchups.txt. Both lists are kept by hand from the news each week.")

with k_tab:
    st.caption("Standard kicker scoring: 3 points for a field goal under 40 yards, 4 for 40-49, "
               "5 for 50+, 1 per extra point, -1 per miss.")
    kickers = phase1.kicker_stats(plays).rename(columns={"fantasy_points": "k_points"}).merge(
        players[["player_id", "player"]], on="player_id", how="left")
    kickers = kickers.merge(status[["player_id", "status"]], on="player_id", how="left")
    if team != "All":
        kickers = kickers[kickers["team"] == team]
    min_fg = st.slider("Minimum field goal attempts", 0, 40, 5)
    kickers = kickers[kickers["fg_attempts"] >= min_fg].sort_values("k_points",
                                                                    ascending=False)
    show_table(kickers, ["player", "team", "status", "games", "fg_made", "fg_attempts", "fg_pct",
                         "fg_0_39", "fg_40_49", "fg_50_plus", "fg_50_attempts", "longest_fg",
                         "xp_made", "xp_attempts", "k_points", "points_per_game"])

with dst_tab:
    st.caption("Standard D/ST scoring: 1 per sack, 2 per interception, fumble recovery, or safety, "
               "6 per defensive or return TD, plus points allowed (10 for a shutout down to -4 "
               "for 35+).")
    defenses = phase1.defense_stats(plays).rename(columns={"fantasy_points": "dst_points"})
    if team != "All":
        defenses = defenses[defenses["team"] == team]
    show_table(defenses, ["team", "games", "sacks", "sack_rate", "interceptions",
                          "fumbles_recovered", "takeaways", "defensive_tds", "safeties",
                          "points_allowed_per_game", "yards_allowed_per_game", "dst_points",
                          "points_per_game"])

with qbs_tab:
    min_pass_yards = st.slider("Minimum passing yards", 0, 3000, 500)
    rows = table[(table["position"] == "QB") & (table["passing_yards"] >= min_pass_yards)]
    rows = rows.sort_values("fantasy_points", ascending=False)
    show_table(rows, ["player", "team", "status", "passing_yards", "passing_tds", "interceptions",
                      "carries", "rushing_yards", "rush_rec_tds", "fantasy_points"])

with receivers_tab:
    position = st.radio("Position", ["All", "WR", "TE", "RB"], horizontal=True)
    min_targets = st.slider("Minimum targets", 0, 100, 20)
    rows = table[(table["position"] != "QB") & (table["targets"] >= min_targets)]
    if position != "All":
        rows = rows[rows["position"] == position]
    show_table(rows, ["player", "team", "position", "snap_share", "targets", "target_share",
                      "first_read_share", "air_yards_share", "adot", "rz_target_share",
                      "catchable_targets", "contested_targets", "drops", "fantasy_points"])

with rbs_tab:
    min_carries = st.slider("Minimum carries", 0, 150, 20)
    rows = table[(table["position"] == "RB") & (table["carries"] >= min_carries)]
    rows = rows.sort_values("rush_share", ascending=False)
    show_table(rows, ["player", "team", "snap_share", "carries", "rush_share",
                      "goal_line_carries", "targets", "target_share", "fantasy_points"])

with buy_low_tab:
    st.write("**Expected points** = what a player's usage (targets, air yards, red zone "
             "targets, carries, goal-line carries) is usually worth across the league. "
             "Players far **below** expected are getting the work but not the points yet, "
             "so they're good trade targets. Players far **above** expected may be "
             "scoring on luck that won't last.")
    min_touches = st.slider("Minimum targets + carries", 0, 200, 40)
    hide_ir = st.checkbox("Hide players on injured reserve", value=False)
    rows = table[(table["position"] != "QB") &
                 ((table["targets"] + table["carries"]) >= min_touches)]
    # Released, retired, and practice-squad players can't help a fantasy team, so they're
    # always hidden. Injured reserve players can come back, so they're shown with a warning.
    allowed = ["Active", "⚠️ Injured reserve"] if not hide_ir else ["Active"]
    rows = rows[rows["status"].isin(allowed)]
    st.caption("⚠️ = on injured reserve. Check the news for how long they're expected to be out.")
    columns = ["player", "team", "position", "status", "targets", "carries", "fantasy_points",
               "expected_points", "points_below_expected"]
    left, right = st.columns(2)
    with left:
        st.subheader("Buy low")
        show_table(rows.sort_values("points_below_expected", ascending=False).head(15), columns)
    with right:
        st.subheader("Sell high")
        show_table(rows.sort_values("points_below_expected").head(15), columns)

@st.cache_data(ttl=60 * 10)
def get_sleeper_leagues(username, season):
    return leagues.sleeper_leagues(username, season)


@st.cache_data(ttl=60 * 10)
def get_league_rosters(platform, league_id, season):
    if platform == "Sleeper":
        return leagues.sleeper_rosters(league_id)
    return leagues.espn_rosters(league_id, season)


with league_tab:
    platform = st.radio("Platform", ["Sleeper", "ESPN"], horizontal=True)
    rosters, lineup = None, None
    try:
        if platform == "Sleeper":
            username = st.text_input("Sleeper username")
            if username:
                user_leagues = get_sleeper_leagues(username, season)
                if not user_leagues:
                    st.info(f"No {season} leagues found for {username}.")
                else:
                    league_name = st.selectbox("League", list(user_leagues))
                    rosters, lineup = get_league_rosters("Sleeper", user_leagues[league_name],
                                                         season)
        else:
            st.caption("Only **public** ESPN leagues can be synced. Your league ID is the number "
                       "after leagueId= in your ESPN league's web address.")
            league_id = st.text_input("ESPN league ID")
            if league_id:
                rosters, lineup = get_league_rosters("ESPN", league_id, season)
    except leagues.LeagueError as problem:
        st.error(str(problem))
    st.caption("Yahoo and NFL.com aren't supported yet.")

    if rosters is not None:
        id_column = "sleeper_id" if platform == "Sleeper" else "espn_id"
        if id_column not in table.columns:
            st.error("The site is still loading updated player data. Refresh in a minute.")
            st.stop()
        # Match each rostered player to our stats using the fantasy site's player ID
        league_table = table.merge(rosters, on=id_column, how="left")
        my_team = st.selectbox("Your team", sorted(rosters["fantasy_team"].unique()))
        st.caption("Tip: set the Weeks filter to the last 3 or 4 weeks to see who's trending.")

        columns = ["player", "team", "position", "status", "snap_share", "target_share",
                   "carries", "fantasy_points", "expected_points"]
        # ----- Power rankings -----
        st.subheader("Power rankings")
        views = (["This week", "Rest of season", "Season so far"] if has_projections
                 else ["Season so far"])
        view = st.radio("Rank by", views, horizontal=True)
        values = None
        if view == "This week":
            values = week_proj.set_index("player_id")["projection"]
        elif view == "Rest of season":
            values = week_proj.set_index("player_id")["ros_points"]
        team_ranks, starters, positions = rankings.power_rankings(league_table, weekly, lineup,
                                                                  values)
        st.caption("Player value = points per game blended with expected points per game. "
                   "Each team's best healthy lineup is scored and the top team is set to 100.")
        st.dataframe(team_ranks.rename(columns={"rank": "Rank", "fantasy_team": "Team",
                                                "score": "Score"}),
                     hide_index=True, column_config={"Score": st.column_config.ProgressColumn(
                         "Score", min_value=0, max_value=100, format="%d")})

        teams = len(team_ranks)
        mine_pos = positions[positions["fantasy_team"] == my_team].copy()
        mine_pos["Rank"] = [f"{rankings.ordinal(r)} of {teams}" for r in mine_pos["rank"]]
        mine_slots = starters[starters["fantasy_team"] == my_team].copy()
        mine_slots["Rank"] = [f"{rankings.ordinal(r)} of {teams}" for r in mine_slots["slot_rank"]]
        my_rank = int(team_ranks.loc[team_ranks["fantasy_team"] == my_team, "rank"].iloc[0])
        st.write(f"**{my_team}** is ranked **{rankings.ordinal(my_rank)} of {teams}**.")

        left, right = st.columns(2)
        with left:
            st.caption("Positional rankings (all your starters at each position)")
            st.dataframe(mine_pos[["position", "Rank", "grade"]].rename(
                columns={"position": "Pos", "grade": "Grade"}), hide_index=True)
        with right:
            st.caption("Starter rankings (each slot vs. the same slot on every team)")
            mine_slots["value"] = mine_slots["value"].round(1)
            st.dataframe(mine_slots[["slot", "player", "value", "Rank", "grade"]].rename(
                columns={"slot": "Slot", "player": "Player", "value": "Value",
                         "grade": "Grade"}), hide_index=True)

        st.subheader("Your roster")
        mine = league_table[league_table["fantasy_team"] == my_team]
        show_table(mine.sort_values("fantasy_points", ascending=False), columns)

        available = league_table[league_table["fantasy_team"].isna() &
                                 (league_table["position"] != "QB") &
                                 (league_table["status"] == "Active")]
        st.subheader("Waiver wire: best available by usage")
        st.caption("Unrostered players ranked by expected points: the work they're getting, "
                   "not the points they've scored.")
        show_table(available.sort_values("expected_points", ascending=False).head(15), columns)

        others = league_table[league_table["fantasy_team"].notna() &
                              (league_table["fantasy_team"] != my_team) &
                              (league_table["position"] != "QB") &
                              (league_table["status"] == "Active")]
        st.subheader("Trade targets: buy low on other teams")
        show_table(others.sort_values("points_below_expected", ascending=False).head(15),
                   ["fantasy_team"] + columns + ["points_below_expected"])

with player_tab:
    names = sorted(table["full_name"].dropna().unique())
    name = st.selectbox("Search for a player", names, index=None,
                        placeholder="Start typing a name, like Puka Nacua")

    if name is None:
        st.info("Pick a player to see all of their stats and weekly charts.")
    else:
        player_rows = table[table["full_name"] == name]
        player_weeks = weekly[weekly["full_name"] == name]

        # Player card: photo, jersey number, height, weight, age, college, experience
        bio = player_rows.iloc[0]
        photo, details = st.columns([1, 4])
        if isinstance(bio["headshot_url"], str):
            photo.image(bio["headshot_url"], width=150)
        with details:
            jersey = f"#{int(bio['jersey_number'])} · " if pd.notna(bio["jersey_number"]) else ""
            st.subheader(f"{name}")
            st.write(f"{jersey}{bio['position']} · {bio['team']}")
            facts = []
            if pd.notna(bio["height"]):
                facts.append(f"{int(bio['height']) // 12}'{int(bio['height']) % 12}\"")
            if pd.notna(bio["weight"]):
                facts.append(f"{int(bio['weight'])} lb")
            if pd.notna(bio["birth_date"]):
                age = (pd.Timestamp.today() - pd.Timestamp(bio["birth_date"])).days // 365
                facts.append(f"Age {age}")
            if pd.notna(bio["years_exp"]):
                facts.append(f"{int(bio['years_exp'])} yrs exp")
            if isinstance(bio["college"], str):
                facts.append(bio["college"].replace(";", ","))
            st.write(" · ".join(facts))

        current_status = player_rows["status"].iloc[0]
        if current_status == "❌ Out for season":
            st.error(f"{name} has been ruled out for the season.")
        elif current_status == "⚠️ Injured reserve":
            st.warning(f"{name} is on injured reserve. Check the news for his expected return.")
        elif current_status != "Active":
            st.warning(f"{name}'s current status: {current_status}.")

        # Totals across the chosen weeks (added up if he played for two teams)
        totals = st.columns(5)
        totals[0].metric(f"{scoring} points", round(player_rows["fantasy_points"].sum(), 1))
        totals[1].metric("Targets", int(player_rows["targets"].sum()))
        totals[2].metric("Carries", int(player_rows["carries"].sum()))
        totals[3].metric("Target share", f"{player_rows['target_share'].max() * 100:.1f}%")
        totals[4].metric("Snap share", f"{player_rows['snap_share'].max() * 100:.1f}%")

        st.subheader("All stats")
        show_table(player_rows, list(COLUMN_NAMES))

        st.subheader("Week by week")
        chart_data = player_weeks.groupby("week")[
            ["fantasy_points", "targets", "carries", "target_share", "snap_share",
             "first_read_share"]].sum()
        chart_data[["target_share", "snap_share", "first_read_share"]] *= 100

        left, right = st.columns(2)
        left.caption(f"{scoring} points")
        left.bar_chart(chart_data["fantasy_points"])
        right.caption("Target share %")
        right.bar_chart(chart_data["target_share"])
        left.caption("Targets and carries")
        left.bar_chart(chart_data[["targets", "carries"]])
        right.caption("Snap share %")
        right.bar_chart(chart_data["snap_share"])
        left.caption("First-read share %")
        left.bar_chart(chart_data["first_read_share"])
