"""
Fantasy Usage Stats - the data
Author: Thomas Youssef

Loads free NFL data and calculates advanced usage stats for every WR, TE, and RB:
  - receiving: target share, air yards share, aDOT, red zone share,
    first-read share, catchable/contested targets, drops
  - rushing: carries, rush share, goal-line carries
  - snap share
  - PPR fantasy points

Data: nflverse (https://github.com/nflverse/nflverse-data).
Charting data (first reads, drops, contested and catchable balls): FTN Data via nflverse,
CC-BY-SA 4.0.
"""

import pandas as pd

SEASON = 2026
BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"
PBP_URL = f"{BASE_URL}/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL = f"{BASE_URL}/players/players.csv"
SNAPS_URL = f"{BASE_URL}/snap_counts/snap_counts_{SEASON}.csv"
FTN_URL = f"{BASE_URL}/ftn_charting/ftn_charting_{SEASON}.csv"

# Only the play-by-play columns this project uses. Loading fewer columns
# makes the site faster and uses less memory.
PBP_COLUMNS = [
    "game_id", "play_id", "season_type", "week", "posteam", "play_type",
    "pass_attempt", "rush_attempt", "two_point_attempt", "complete_pass",
    "passer_player_id", "receiver_player_id", "rusher_player_id",
    "lateral_receiver_player_id", "lateral_rusher_player_id", "td_player_id",
    "fumbled_1_player_id", "air_yards", "yardline_100",
    "passing_yards", "receiving_yards", "rushing_yards",
    "lateral_receiving_yards", "lateral_rushing_yards",
    "touchdown", "pass_touchdown", "rush_touchdown", "return_touchdown",
    "interception", "fumble_lost", "two_point_conv_result",
]
FTN_COLUMNS = ["nflverse_game_id", "nflverse_play_id", "read_thrown",
               "is_catchable_ball", "is_contested_ball", "is_drop"]


# ---------- Step 1: load the data ----------

def load_plays(source=PBP_URL, ftn_source=FTN_URL):
    """One season of play-by-play (one row per play, regular season only),
    with FTN charting columns attached to each play."""
    plays = pd.read_csv(source, usecols=PBP_COLUMNS, low_memory=False)
    plays = plays[plays["season_type"] == "REG"]

    ftn = pd.read_csv(ftn_source, usecols=FTN_COLUMNS)
    plays = plays.merge(ftn, left_on=["game_id", "play_id"],
                        right_on=["nflverse_game_id", "nflverse_play_id"], how="left")
    for col in ["is_catchable_ball", "is_contested_ball", "is_drop"]:
        plays[col] = plays[col].fillna(False).astype(int)
    return plays.drop(columns=["nflverse_game_id", "nflverse_play_id"])


def load_players(source=PLAYERS_URL):
    """Each player's ID, name, and position."""
    players = pd.read_csv(source, usecols=["gsis_id", "pfr_id", "short_name",
                                           "display_name", "position"])
    return players.rename(columns={"gsis_id": "player_id", "short_name": "player",
                                   "display_name": "full_name"})


def load_snaps(source=SNAPS_URL, players=None):
    """Offensive snaps per player per game, matched to the same player IDs as the plays."""
    snaps = pd.read_csv(source, usecols=["game_id", "game_type", "week", "team",
                                         "pfr_player_id", "offense_snaps"])
    snaps = snaps[snaps["game_type"] == "REG"]
    ids = players[["pfr_id", "player_id"]].dropna()
    return snaps.merge(ids, left_on="pfr_player_id", right_on="pfr_id")


# ---------- Step 2: receiving stats ----------

def get_targets(plays):
    """Every pass thrown to a player (not two-point tries)."""
    return plays[(plays["pass_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                 plays["receiver_player_id"].notna()]


def target_share(plays):
    """Target share = player targets / team targets."""
    targets = get_targets(plays)
    per_player = (targets.groupby(["posteam", "receiver_player_id"])
                  .size().reset_index(name="targets"))
    per_team = targets.groupby("posteam").size().rename("team_targets")

    table = per_player.join(per_team, on="posteam")
    table["target_share"] = table["targets"] / table["team_targets"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})


def air_yards_share(plays):
    """Air yards = how far the ball travels in the air. Share = player air yards / team air yards."""
    targets = get_targets(plays)
    per_player = (targets.groupby(["posteam", "receiver_player_id"])["air_yards"]
                  .sum().reset_index(name="air_yards"))
    per_team = targets.groupby("posteam")["air_yards"].sum().rename("team_air_yards")

    table = per_player.join(per_team, on="posteam")
    table["air_yards_share"] = table["air_yards"] / table["team_air_yards"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})


def red_zone_share(plays):
    """Red zone = inside the opponent's 20-yard line, where most TDs happen."""
    targets = get_targets(plays)
    targets = targets[targets["yardline_100"] <= 20]

    per_player = (targets.groupby(["posteam", "receiver_player_id"])
                  .size().reset_index(name="rz_targets"))
    per_team = targets.groupby("posteam").size().rename("rz_team_targets")

    table = per_player.join(per_team, on="posteam")
    table["rz_target_share"] = table["rz_targets"] / table["rz_team_targets"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})


def first_read_share(plays):
    """First-read target = the QB threw to the first receiver he looked at
    (FTN's read_thrown = "1"). Share = player first-read targets / team first-read targets."""
    targets = get_targets(plays)
    targets = targets[targets["read_thrown"] == "1"]

    per_player = (targets.groupby(["posteam", "receiver_player_id"])
                  .size().reset_index(name="first_read_targets"))
    per_team = targets.groupby("posteam").size().rename("team_first_read_targets")

    table = per_player.join(per_team, on="posteam")
    table["first_read_share"] = table["first_read_targets"] / table["team_first_read_targets"]
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})


def ball_quality(plays):
    """From FTN charting: how many targets were catchable, contested, or dropped."""
    targets = get_targets(plays)
    table = (targets.groupby(["posteam", "receiver_player_id"])
             [["is_catchable_ball", "is_contested_ball", "is_drop"]].sum().reset_index())
    table = table.rename(columns={"is_catchable_ball": "catchable_targets",
                                  "is_contested_ball": "contested_targets",
                                  "is_drop": "drops"})
    return table.rename(columns={"posteam": "team", "receiver_player_id": "player_id"})


# ---------- Step 3: rushing stats ----------

def rushing_share(plays):
    """Carries = running plays. Rush share = player carries / team carries.
    Goal-line carries = carries inside the opponent's 5-yard line."""
    runs = plays[(plays["rush_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                 plays["rusher_player_id"].notna()]

    per_player = (runs.groupby(["posteam", "rusher_player_id"])
                  .size().reset_index(name="carries"))
    per_team = runs.groupby("posteam").size().rename("team_carries")
    table = per_player.join(per_team, on="posteam")
    table["rush_share"] = table["carries"] / table["team_carries"]

    goal_line = runs[runs["yardline_100"] <= 5]
    per_player_gl = (goal_line.groupby(["posteam", "rusher_player_id"])
                     .size().rename("goal_line_carries"))
    table = table.join(per_player_gl, on=["posteam", "rusher_player_id"])
    table["goal_line_carries"] = table["goal_line_carries"].fillna(0)

    return table.rename(columns={"posteam": "team", "rusher_player_id": "player_id"})


# ---------- Step 4: snap share ----------

def snap_share(snaps):
    """Snap share = player offensive snaps / team offensive snaps.
    A team's snaps in a game = the most snaps any of its players had (linemen play every snap)."""
    team_per_game = snaps.groupby(["game_id", "team"])["offense_snaps"].max()
    team_snaps = team_per_game.groupby("team").sum().rename("team_snaps")

    per_player = (snaps.groupby(["team", "player_id"])["offense_snaps"]
                  .sum().reset_index(name="snaps"))
    table = per_player.join(team_snaps, on="team")
    table["snap_share"] = table["snaps"] / table["team_snaps"]
    return table


# ---------- Step 5: PPR fantasy points ----------

def fantasy_points(plays):
    """PPR scoring: 1 per catch, 0.1 per rush/receiving yard, 0.04 per passing yard,
    6 per rush/receiving/return TD, 4 per passing TD, 2 per two-point conversion,
    -2 per interception or lost fumble.
    Points are counted per team, so a player traded mid-season gets a separate row for each team."""
    def total(id_col, value_col, rows=plays):
        return rows.groupby(["posteam", id_col])[value_col].sum().rename_axis(["team", "player_id"])

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
        scoring.groupby(["posteam", "td_player_id"]).size().rename_axis(["team", "player_id"]) * 6,
        total("passer_player_id", "made", two_pt) * 2,
        total("receiver_player_id", "made", two_pt) * 2,
        total("rusher_player_id", "made", two_pt) * 2,
        total("fumbled_1_player_id", "fumble_lost", offense) * -2,  # not on kicks/punts
    ], axis=1).fillna(0)

    points = points.sum(axis=1)
    return points.rename("ppr_points").reset_index()


# ---------- Step 6: put it together ----------

def build_table(plays, players, snaps):
    """One row per player per team, with every stat."""
    receiving = target_share(plays)
    rushing = rushing_share(plays)

    # Start with everyone who had a target or a carry
    table = pd.concat([receiving[["team", "player_id"]], rushing[["team", "player_id"]]])
    table = table.drop_duplicates()
    table = table.merge(players[["player_id", "player", "full_name", "position"]],
                        on="player_id", how="left")
    table = table[table["position"].isin(["WR", "TE", "RB"])]

    for stats in [receiving, air_yards_share(plays), red_zone_share(plays),
                  first_read_share(plays), ball_quality(plays), rushing, snap_share(snaps)]:
        table = table.merge(stats, on=["team", "player_id"], how="left")

    # Players with no targets (or no carries) get 0 instead of an empty value
    counts = ["targets", "target_share", "air_yards", "air_yards_share", "rz_targets",
              "rz_target_share", "first_read_targets", "first_read_share",
              "catchable_targets", "contested_targets", "drops",
              "carries", "rush_share", "goal_line_carries", "snaps", "snap_share"]
    table[counts] = table[counts].fillna(0)
    table["adot"] = table["air_yards"] / table["targets"].where(table["targets"] > 0)

    table = table.merge(fantasy_points(plays), on=["team", "player_id"], how="left")
    table["ppr_points"] = table["ppr_points"].fillna(0)
    return table.sort_values("target_share", ascending=False)


def build_weekly(plays, players, snaps):
    """The same table, built separately for each week (used for the player charts)."""
    weeks = []
    for week in sorted(plays["week"].unique()):
        week_table = build_table(plays[plays["week"] == week], players,
                                 snaps[snaps["week"] == week])
        weeks.append(week_table.assign(week=week))
    return pd.concat(weeks)


if __name__ == "__main__":
    print(f"Loading {SEASON} data (this takes about 30 seconds)...")
    players = load_players()
    plays = load_plays()
    snaps = load_snaps(players=players)
    table = build_table(plays, players, snaps)
    print(f"Weeks included: {plays['week'].min()}-{plays['week'].max()}\n")

    shown = table[["player", "team", "position", "targets", "target_share",
                   "first_read_share", "snap_share", "ppr_points"]].head(20)
    print(shown.round(3).to_string(index=False))
