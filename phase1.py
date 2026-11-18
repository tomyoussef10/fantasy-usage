"""
Fantasy Usage Stats - Phase 1
Author: Thomas Youssef

Loads free NFL play-by-play data from nflverse and calculates, for every
WR, TE, and RB:
  - targets and target share (their share of their team's targets)
  - PPR fantasy points

Data: nflverse (https://github.com/nflverse/nflverse-data)
"""

import pandas as pd

SEASON = 2026
PBP_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"


# ---------- Step 1: load the data ----------

def load_plays(source=PBP_URL):
    """Load one season of play-by-play: one row per play, regular season only."""
    plays = pd.read_csv(source, low_memory=False)
    return plays[plays["season_type"] == "REG"]


def load_positions(source=PLAYERS_URL):
    """Map each player ID to a position (WR, TE, RB, QB...)."""
    players = pd.read_csv(source, usecols=["gsis_id", "position"])
    return players.rename(columns={"gsis_id": "player_id"})


# ---------- Step 2: targets and target share ----------

def target_share(plays):
    """A target is a pass thrown to a player. Target share = player targets / team targets."""
    targets = plays[(plays["pass_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                    plays["receiver_player_id"].notna()]

    per_player = (targets.groupby(["posteam", "receiver_player_id", "receiver_player_name"])
                  .size().reset_index(name="targets"))
    per_team = targets.groupby("posteam").size().rename("team_targets")

    table = per_player.join(per_team, on="posteam")
    table["target_share"] = table["targets"] / table["team_targets"]
    return table.rename(columns={"posteam": "team",
                                 "receiver_player_id": "player_id",
                                 "receiver_player_name": "player"})


def air_yards_share(plays):
    """Air yards = how far the ball travels in the air. Share = player air yards / team air yards."""
    targets = plays[(plays["pass_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                    plays["receiver_player_id"].notna()]

    per_player = (targets.groupby(["posteam", "receiver_player_id"])["air_yards"]
                  .sum().reset_index(name="air_yards"))
    per_team = targets.groupby("posteam")["air_yards"].sum().rename("team_air_yards")

    table = per_player.join(per_team, on="posteam")
    table["air_yards_share"] = table["air_yards"] / table["team_air_yards"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})

def red_zone_share(plays):
    """Red zone = inside the opponent's 20-yard line, where most TDs happen."""
    targets = plays[(plays["pass_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                    plays["receiver_player_id"].notna()]
    targets = targets[targets["yardline_100"] <= 20]

    per_player = (targets.groupby(["posteam", "receiver_player_id"])
                  .size().reset_index(name="rz_targets"))
    per_team = targets.groupby("posteam").size().rename("rz_team_targets")

    table = per_player.join(per_team, on="posteam")
    table["rz_target_share"] = table["rz_targets"] / table["rz_team_targets"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})

# ---------- Step 3: PPR fantasy points ----------

def fantasy_points(plays):
    """PPR scoring: 1 per catch, 0.1 per rush/receiving yard, 0.04 per passing yard,
    6 per rush/receiving/return TD, 4 per passing TD, 2 per two-point conversion,
    -2 per interception or lost fumble."""
    def total(id_col, value_col, rows=plays):
        return rows.groupby(id_col)[value_col].sum()

    # Touchdowns scored by the ball carrier (not fumble-recovery or defensive TDs)
    scoring = plays[(plays["touchdown"] == 1) &
                    ((plays["rush_touchdown"] == 1) | (plays["pass_touchdown"] == 1) |
                     (plays["return_touchdown"] == 1))]
    two_pt = plays[plays["two_point_conv_result"] == "success"].assign(made=1)
    offense = plays[plays["play_type"].isin(["pass", "run", "qb_kneel", "qb_spike"])]

    points = pd.concat([
        total("receiver_player_id", "complete_pass") * 1,            # catches
        total("receiver_player_id", "receiving_yards") * 0.1,
        total("lateral_receiver_player_id", "lateral_receiving_yards") * 0.1,
        total("rusher_player_id", "rushing_yards") * 0.1,
        total("lateral_rusher_player_id", "lateral_rushing_yards") * 0.1,
        total("passer_player_id", "passing_yards") * 0.04,
        total("passer_player_id", "pass_touchdown") * 4,
        total("passer_player_id", "interception") * -2,
        scoring.groupby("td_player_id").size() * 6,                    # player who scored
        total("passer_player_id", "made", two_pt) * 2,
        total("receiver_player_id", "made", two_pt) * 2,
        total("rusher_player_id", "made", two_pt) * 2,
        total("fumbled_1_player_id", "fumble_lost", offense) * -2,  # not on kicks/punts
    ], axis=1).fillna(0)

    points = points.sum(axis=1)
    return points.rename("ppr_points").rename_axis("player_id").reset_index()


# ---------- Step 4: put it together ----------

def build_table(plays, positions):
    table = target_share(plays).merge(positions, on="player_id", how="left")
    table = table.merge(air_yards_share(plays), on=["team", "player_id"], how="left")
    table["adot"] = table["air_yards"] / table["targets"]
    table = table.merge(red_zone_share(plays), on=["team", "player_id"], how="left")
    table[["rz_targets", "rz_target_share"]] = table[["rz_targets", "rz_target_share"]].fillna(0)
    table = table[table["position"].isin(["WR", "TE", "RB"])]
    table = table.merge(fantasy_points(plays), on="player_id", how="left")
    return table.sort_values("target_share", ascending=False)

if __name__ == "__main__":
    print(f"Loading {SEASON} play-by-play (this takes about 30 seconds)...")
    plays = load_plays()
    positions = load_positions()
    table = build_table(plays, positions)
    print(f"Weeks included: {plays['week'].min()}-{plays['week'].max()}\n")

    shown = table[["player", "team", "position", "targets", "target_share", "ppr_points"]].head(20).copy()
    shown["target_share"] = (shown["target_share"] * 100).round(1).astype(str) + "%"
    shown["ppr_points"] = shown["ppr_points"].round(1)
    print("Top 20 by target share (WR/TE/RB):")
    print(shown.to_string(index=False))

    table.to_csv(f"usage_{SEASON}.csv", index=False)
    print(f"\nSaved full table to usage_{SEASON}.csv")
