"""
Fantasy Usage Stats - Phase 2: the website
Run with:  python3 -m streamlit run app.py
"""

import streamlit as st
import phase1

st.set_page_config(page_title="Fantasy Usage Stats", layout="wide")
st.title("Fantasy Usage Stats")
st.caption(f"{phase1.SEASON} regular season · Data: nflverse")


# Part 1: load the data once, then reuse it
@st.cache_data
def get_table():
    plays = phase1.load_plays()
    positions = phase1.load_positions()
    return phase1.build_table(plays, positions)


with st.spinner("Loading play-by-play data (about 30 seconds the first time)..."):
    table = get_table()


# Part 2: a filter the visitor can change
position = st.selectbox("Position", ["All", "WR", "TE", "RB"])
if position != "All":
    table = table[table["position"] == position]

team = st.selectbox("Team", ["All"] + sorted(table["team"].unique()))
if team != "All":
    table = table[table["team"] == team]
min_targets = st.slider("Minimum targets", 0, 100, 20)
table = table[table["targets"] >= min_targets]

# Part 3: show the table
shown = table[["player", "team", "position", "targets", "target_share", "air_yards_share", "adot", "rz_target_share", "ppr_points"]].copy()
shown["target_share"] = (shown["target_share"] * 100).round(1)
shown["air_yards_share"] = (shown["air_yards_share"] * 100).round(1)
shown["adot"] = shown["adot"].round(1)
shown["rz_target_share"] = (shown["rz_target_share"] * 100).round(1)   # NEW
shown["ppr_points"] = shown["ppr_points"].round(1)
shown = shown.rename(columns={
    "player": "Player", "team": "Team", "position": "Pos", "targets": "Targets",
    "target_share": "Target share %", "ppr_points": "PPR points",
    "air_yards_share": "Air yards share %", "adot": "aDOT",
    "rz_target_share": "RZ target share %",                            # NEW
})
st.dataframe(shown, hide_index=True)