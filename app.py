"""
Fantasy Usage Stats - the website
Run with:  python3 -m streamlit run app.py
"""

import streamlit as st
import phase1
import news

st.set_page_config(page_title="Fantasy Usage Stats", layout="wide")
st.title("Fantasy Usage Stats")
st.caption(f"{phase1.SEASON} regular season · Data: nflverse · "
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
    player_news, headlines_col = st.columns(2)
    with player_news:
        st.subheader("Player news (RotoWire)")
        show_news("RotoWire", show_times=True)
    with headlines_col:
        st.subheader("Headlines (ESPN)")
        show_news("ESPN", show_times=False)
    st.link_button("Breaking updates: Underdog NFL on X", "https://x.com/UnderdogNFL")


# ---------- Part 1: load the data once a day, then reuse it ----------
@st.cache_data(ttl=60 * 60 * 24)  # refresh once a day
def get_data():
    players = phase1.load_players()
    plays = phase1.load_plays()
    snaps = phase1.load_snaps(players=players)
    weekly = phase1.build_weekly(plays, players, snaps)
    status = phase1.load_status()
    return plays, players, snaps, weekly, status


with st.spinner("Loading NFL data (about 30 seconds the first time)..."):
    plays, players, snaps, weekly, status = get_data()


# ---------- Part 2: filters in the sidebar (they apply to every tab) ----------
st.sidebar.header("Filters")
first, last = int(plays["week"].min()), int(plays["week"].max())
weeks = st.sidebar.slider("Weeks", first, last, (first, last))
plays = plays[plays["week"].between(weeks[0], weeks[1])]
snaps = snaps[snaps["week"].between(weeks[0], weeks[1])]
weekly = weekly[weekly["week"].between(weeks[0], weeks[1])]
table = phase1.build_table(plays, players, snaps)
table = table.merge(status, on="player_id", how="left")
table["status"] = table["status"].fillna("Unknown")

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
    "ppr_points": "PPR points", "expected_points": "Expected points",
    "points_below_expected": "Points below expected",
}
PERCENT_COLUMNS = ["snap_share", "target_share", "first_read_share", "air_yards_share",
                   "rz_target_share", "rush_share"]
COUNT_COLUMNS = ["targets", "catchable_targets", "contested_targets", "drops",
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
receivers_tab, rbs_tab, buy_low_tab, player_tab = st.tabs(
    ["Receivers", "Running backs", "Buy low", "Player search"])

with receivers_tab:
    position = st.radio("Position", ["All", "WR", "TE", "RB"], horizontal=True)
    min_targets = st.slider("Minimum targets", 0, 100, 20)
    rows = table[table["targets"] >= min_targets]
    if position != "All":
        rows = rows[rows["position"] == position]
    show_table(rows, ["player", "team", "position", "snap_share", "targets", "target_share",
                      "first_read_share", "air_yards_share", "adot", "rz_target_share",
                      "catchable_targets", "contested_targets", "drops", "ppr_points"])

with rbs_tab:
    min_carries = st.slider("Minimum carries", 0, 150, 20)
    rows = table[(table["position"] == "RB") & (table["carries"] >= min_carries)]
    rows = rows.sort_values("rush_share", ascending=False)
    show_table(rows, ["player", "team", "snap_share", "carries", "rush_share",
                      "goal_line_carries", "targets", "target_share", "ppr_points"])

with buy_low_tab:
    st.write("**Expected points** = what a player's usage (targets, air yards, red zone "
             "targets, carries, goal-line carries) is usually worth across the league. "
             "Players far **below** expected are getting the work but not the points yet, "
             "so they're good trade targets. Players far **above** expected may be "
             "scoring on luck that won't last.")
    min_touches = st.slider("Minimum targets + carries", 0, 200, 40)
    active_only = st.checkbox("Only show active players (hide injured reserve, released, etc.)",
                              value=True)
    rows = table[(table["targets"] + table["carries"]) >= min_touches]
    if active_only:
        rows = rows[rows["status"] == "Active"]
    columns = ["player", "team", "position", "status", "targets", "carries", "ppr_points",
               "expected_points", "points_below_expected"]
    left, right = st.columns(2)
    with left:
        st.subheader("Buy low")
        show_table(rows.sort_values("points_below_expected", ascending=False).head(15), columns)
    with right:
        st.subheader("Sell high")
        show_table(rows.sort_values("points_below_expected").head(15), columns)

with player_tab:
    names = sorted(table["full_name"].dropna().unique())
    name = st.selectbox("Search for a player", names, index=None,
                        placeholder="Start typing a name, like Puka Nacua")

    if name is None:
        st.info("Pick a player to see all of their stats and weekly charts.")
    else:
        player_rows = table[table["full_name"] == name]
        player_weeks = weekly[weekly["full_name"] == name]

        # Totals across the chosen weeks (added up if he played for two teams)
        totals = st.columns(5)
        totals[0].metric("PPR points", round(player_rows["ppr_points"].sum(), 1))
        totals[1].metric("Targets", int(player_rows["targets"].sum()))
        totals[2].metric("Carries", int(player_rows["carries"].sum()))
        totals[3].metric("Target share", f"{player_rows['target_share'].max() * 100:.1f}%")
        totals[4].metric("Snap share", f"{player_rows['snap_share'].max() * 100:.1f}%")

        st.subheader("All stats")
        show_table(player_rows, list(COLUMN_NAMES))

        st.subheader("Week by week")
        chart_data = player_weeks.groupby("week")[
            ["ppr_points", "targets", "carries", "target_share", "snap_share",
             "first_read_share"]].sum()
        chart_data[["target_share", "snap_share", "first_read_share"]] *= 100

        left, right = st.columns(2)
        left.caption("PPR points")
        left.bar_chart(chart_data["ppr_points"])
        right.caption("Target share %")
        right.bar_chart(chart_data["target_share"])
        left.caption("Targets and carries")
        left.bar_chart(chart_data[["targets", "carries"]])
        right.caption("Snap share %")
        right.bar_chart(chart_data["snap_share"])
        left.caption("First-read share %")
        left.bar_chart(chart_data["first_read_share"])
