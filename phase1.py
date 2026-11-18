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

import numpy as np
import pandas as pd

# Bump this number whenever the loaded data gets new columns. The website includes it in
# its cache key, so old saved data is thrown away automatically after an update.
DATA_VERSION = 3

SEASON = 2026                       # the current season (the site's default)
SEASONS = [2026, 2025]              # seasons visitors can pick
BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"
PLAYERS_URL = f"{BASE_URL}/players/players.csv"


def data_url(kind, season):
    """Web address of one nflverse data file for one season."""
    files = {
        "pbp": f"pbp/play_by_play_{season}.csv.gz",
        "snaps": f"snap_counts/snap_counts_{season}.csv",
        "ftn": f"ftn_charting/ftn_charting_{season}.csv",
        "rosters": f"weekly_rosters/roster_weekly_{season}.csv",
    }
    return f"{BASE_URL}/{files[kind]}"


# Roster status codes from the weekly rosters file, in plain English
STATUS_NAMES = {"ACT": "Active", "RES": "Injured reserve", "INA": "Inactive",
                "DEV": "Practice squad", "CUT": "Released", "RET": "Retired",
                "EXE": "Exempt", "TRD": "Traded", "TRC": "Traded", "TRT": "Traded"}

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
    # kickers and defenses
    "kicker_player_id", "field_goal_attempt", "field_goal_result", "kick_distance",
    "extra_point_attempt", "extra_point_result", "defteam", "sack", "safety", "td_team",
    "home_team", "away_team", "total_home_score", "total_away_score", "yards_gained",
    "qb_dropback",
]
FTN_COLUMNS = ["nflverse_game_id", "nflverse_play_id", "read_thrown",
               "is_catchable_ball", "is_contested_ball", "is_drop"]


# ---------- Step 1: load the data ----------

def load_plays(season=SEASON):
    """One season of play-by-play (one row per play, regular season only),
    with FTN charting columns attached to each play."""
    plays = pd.read_csv(data_url("pbp", season), usecols=PBP_COLUMNS, low_memory=False)
    plays = plays[plays["season_type"] == "REG"]

    ftn = pd.read_csv(data_url("ftn", season), usecols=FTN_COLUMNS)
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


def load_snaps(players, season=SEASON):
    """Offensive snaps per player per game, matched to the same player IDs as the plays."""
    snaps = pd.read_csv(data_url("snaps", season), usecols=["game_id", "game_type", "week", "team",
                                         "pfr_player_id", "offense_snaps"])
    snaps = snaps[snaps["game_type"] == "REG"]
    ids = players[["pfr_id", "player_id"]].dropna()
    return snaps.merge(ids, left_on="pfr_player_id", right_on="pfr_id")


def load_status(season=SEASON):
    """Each player's current roster status (Active, Injured reserve, ...) and bio
    (photo, jersey number, height, weight, college, experience), taken from the most
    recent week of the weekly rosters file."""
    rosters = pd.read_csv(data_url("rosters", season),
                          usecols=["gsis_id", "week", "game_type", "status", "jersey_number",
                                   "height", "weight", "college", "years_exp",
                                   "birth_date", "headshot_url", "sleeper_id", "espn_id"])
    rosters = rosters[rosters["game_type"] == "REG"].drop(columns="game_type")
    latest = rosters.sort_values("week").drop_duplicates("gsis_id", keep="last")
    latest["status"] = latest["status"].map(STATUS_NAMES).fillna(latest["status"])
    # Fantasy-site player IDs as text (like "4035"), used to match league rosters
    for col in ["sleeper_id", "espn_id"]:
        latest[col] = latest[col].astype("Int64").astype(str).replace("<NA>", None)
    return latest.rename(columns={"gsis_id": "player_id"}).drop(columns="week")


# ---------- Step 2: receiving stats ----------

def get_targets(plays):
    """Every pass thrown to a player (not two-point tries)."""
    return plays[(plays["pass_attempt"] == 1) & (plays["two_point_attempt"] == 0) &
                 plays["receiver_player_id"].notna()]


def target_share(plays):
    """Target share = player targets / team targets."""
    targets = get_targets(plays)
    per_player = (targets.groupby(["posteam", "receiver_player_id"])
                  .agg(targets=("complete_pass", "size"), receptions=("complete_pass", "sum"))
                  .reset_index())
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


# ---------- Step 5: fantasy points ----------

# Point values for each scoring stat. PPR is the default; the website lets visitors change them.
PPR_SCORING = {
    "catches": 1.0, "receiving_yards": 0.1, "rushing_yards": 0.1, "passing_yards": 0.04,
    "passing_tds": 4.0, "rush_rec_tds": 6.0, "interceptions": -2.0, "fumbles_lost": -2.0,
    "two_point_conversions": 2.0,
}
SCORING_STATS = list(PPR_SCORING)


def scoring_stats(plays):
    """Each player's raw scoring stats per team (catches, yards, TDs, turnovers, 2-pt).
    Points are then worked out from these with any scoring settings (see score())."""
    def total(id_col, value_col, rows=plays):
        return rows.groupby(["posteam", id_col])[value_col].sum().rename_axis(["team", "player_id"])

    # Touchdowns scored by the ball carrier (not fumble-recovery or defensive TDs)
    scoring = plays[(plays["touchdown"] == 1) &
                    ((plays["rush_touchdown"] == 1) | (plays["pass_touchdown"] == 1) |
                     (plays["return_touchdown"] == 1))]
    two_pt = plays[plays["two_point_conv_result"] == "success"].assign(made=1)
    offense = plays[plays["play_type"].isin(["pass", "run", "qb_kneel", "qb_spike"])]

    stats = pd.concat({
        "catches": total("receiver_player_id", "complete_pass"),
        "receiving_yards": total("receiver_player_id", "receiving_yards").add(
            total("lateral_receiver_player_id", "lateral_receiving_yards"), fill_value=0),
        "rushing_yards": total("rusher_player_id", "rushing_yards").add(
            total("lateral_rusher_player_id", "lateral_rushing_yards"), fill_value=0),
        "passing_yards": total("passer_player_id", "passing_yards"),
        "passing_tds": total("passer_player_id", "pass_touchdown"),
        "rush_rec_tds": scoring.groupby(["posteam", "td_player_id"]).size()
                               .rename_axis(["team", "player_id"]),
        "interceptions": total("passer_player_id", "interception"),
        "fumbles_lost": total("fumbled_1_player_id", "fumble_lost", offense),  # not on kicks/punts
        "two_point_conversions": total("passer_player_id", "made", two_pt).add(
            total("receiver_player_id", "made", two_pt), fill_value=0).add(
            total("rusher_player_id", "made", two_pt), fill_value=0),
    }, axis=1).fillna(0)
    return stats.reset_index()


def score(table, settings=PPR_SCORING):
    """Fantasy points = each scoring stat times its point value, added up."""
    return sum(table[stat] * value for stat, value in settings.items())


# ---------- Step 5b: kickers and team defenses ----------

def kicker_stats(plays):
    """Field goals by distance, extra points, accuracy, and standard fantasy points:
    3 for a FG under 40 yards, 4 for 40-49, 5 for 50+, 1 per extra point,
    -1 per missed FG or extra point."""
    fg = plays[plays["field_goal_attempt"] == 1]
    xp = plays[plays["extra_point_attempt"] == 1]
    made = fg["field_goal_result"] == "made"
    fg = fg.assign(made=made.astype(int),
                   made_0_39=(made & (fg["kick_distance"] < 40)).astype(int),
                   made_40_49=(made & fg["kick_distance"].between(40, 49)).astype(int),
                   made_50=(made & (fg["kick_distance"] >= 50)).astype(int),
                   att_50=(fg["kick_distance"] >= 50).astype(int),
                   long=fg["kick_distance"].where(made))
    kicks = fg.groupby(["posteam", "kicker_player_id"]).agg(
        fg_attempts=("made", "size"), fg_made=("made", "sum"), fg_0_39=("made_0_39", "sum"),
        fg_40_49=("made_40_49", "sum"), fg_50_plus=("made_50", "sum"),
        fg_50_attempts=("att_50", "sum"), longest_fg=("long", "max"),
        games=("game_id", "nunique"))
    xps = xp.assign(good=(xp["extra_point_result"] == "good").astype(int)).groupby(
        ["posteam", "kicker_player_id"]).agg(xp_attempts=("good", "size"), xp_made=("good", "sum"),
                                             xp_games=("game_id", "nunique"))
    table = kicks.join(xps, how="outer").fillna(0).reset_index()
    table["games"] = table[["games", "xp_games"]].max(axis=1)
    table["fg_pct"] = table["fg_made"] / table["fg_attempts"].where(table["fg_attempts"] > 0)
    table["fantasy_points"] = (3 * table["fg_0_39"] + 4 * table["fg_40_49"] + 5 * table["fg_50_plus"]
                               + table["xp_made"]
                               - (table["fg_attempts"] - table["fg_made"])
                               - (table["xp_attempts"] - table["xp_made"]))
    table["points_per_game"] = table["fantasy_points"] / table["games"]
    return table.rename(columns={"posteam": "team", "kicker_player_id": "player_id"}).drop(
        columns="xp_games")


def points_allowed_score(points):
    """Standard fantasy points for points allowed in one game."""
    for limit, score in [(0, 10), (6, 7), (13, 4), (20, 1), (27, 0), (34, -1)]:
        if points <= limit:
            return score
    return -4


def defense_stats(plays):
    """Team defense (D/ST) stats and standard fantasy points: 1 per sack, 2 per interception,
    fumble recovery, or safety, 6 per defensive or return TD, plus points for points allowed."""
    # Final score of every game, from the last play
    finals = plays.sort_values("play_id").groupby("game_id").last()
    games = pd.concat([
        pd.DataFrame({"team": finals["home_team"], "points_allowed": finals["total_away_score"]}),
        pd.DataFrame({"team": finals["away_team"], "points_allowed": finals["total_home_score"]}),
    ])
    games["pa_points"] = games["points_allowed"].apply(points_allowed_score)
    per_team = games.groupby("team").agg(games=("points_allowed", "size"),
                                         points_allowed=("points_allowed", "sum"),
                                         pa_points=("pa_points", "sum"))

    # Only real offensive plays, so fumbles on punt and kick returns aren't credited wrongly
    on_defense = plays[plays["defteam"].notna() & plays["play_type"].isin(["pass", "run"])]
    d = on_defense.groupby("defteam").agg(
        sacks=("sack", "sum"), interceptions=("interception", "sum"),
        fumbles_recovered=("fumble_lost", "sum"), safeties=("safety", "sum"),
        yards_allowed=("yards_gained", "sum"), dropbacks_faced=("qb_dropback", "sum"))
    # D/ST touchdowns: scored by the team that wasn't on offense (pick-sixes, fumble returns,
    # punt returns), plus kickoff and punt return TDs
    def_tds = plays[(plays["touchdown"] == 1) &
                    ((plays["td_team"] == plays["defteam"]) | (plays["return_touchdown"] == 1))]
    d["defensive_tds"] = def_tds.groupby("td_team").size()

    table = per_team.join(d).fillna(0).reset_index().rename(columns={"index": "team"})
    table["sack_rate"] = table["sacks"] / table["dropbacks_faced"].where(table["dropbacks_faced"] > 0)
    table["takeaways"] = table["interceptions"] + table["fumbles_recovered"]
    table["points_allowed_per_game"] = table["points_allowed"] / table["games"]
    table["yards_allowed_per_game"] = table["yards_allowed"] / table["games"]
    table["fantasy_points"] = (table["sacks"] + 2 * table["interceptions"]
                               + 2 * table["fumbles_recovered"] + 2 * table["safeties"]
                               + 6 * table["defensive_tds"] + table["pa_points"])
    table["points_per_game"] = table["fantasy_points"] / table["games"]
    return table.sort_values("fantasy_points", ascending=False)


# ---------- Step 6: expected points (for the buy low list) ----------

USAGE_COLUMNS = ["targets", "air_yards", "rz_targets", "carries", "goal_line_carries"]


def add_expected_points(table, points_column="ppr_points", min_touches=10):
    """Expected PPR points = what a player's usage is usually worth.

    A linear regression (least squares) learns how many points each target,
    air yard, red zone target, carry, and goal-line carry is worth on average
    across the league. Multiplying a player's usage by those values gives his
    expected points. Points below expected = expected - actual: a positive number
    means he scored less than his usage suggests (a "buy low")."""
    table = table.copy()
    # QBs score mostly from passing, which these usage columns don't measure, so they're left out
    skill = table["position"] != "QB"
    fit = table[skill & ((table["targets"] + table["carries"]) >= min_touches)]
    if len(fit) < len(USAGE_COLUMNS):
        table["expected_points"] = np.nan
    else:
        values, *_ = np.linalg.lstsq(fit[USAGE_COLUMNS].to_numpy(float),
                                     fit[points_column].to_numpy(float), rcond=None)
        table["expected_points"] = table[USAGE_COLUMNS].to_numpy(float) @ values
        table.loc[~skill, "expected_points"] = np.nan
    table["points_below_expected"] = table["expected_points"] - table[points_column]
    return table


# ---------- Step 7: put it together ----------

def build_table(plays, players, snaps):
    """One row per player per team, with every stat."""
    receiving = target_share(plays)
    rushing = rushing_share(plays)

    # Start with everyone who had a target or a carry
    passers = (plays[plays["passer_player_id"].notna()][["posteam", "passer_player_id"]]
               .rename(columns={"posteam": "team", "passer_player_id": "player_id"}))
    table = pd.concat([receiving[["team", "player_id"]], rushing[["team", "player_id"]], passers])
    table = table.drop_duplicates()
    table = table.merge(players[["player_id", "player", "full_name", "position"]],
                        on="player_id", how="left")
    table = table[table["position"].isin(["QB", "WR", "TE", "RB"])]

    for stats in [receiving, air_yards_share(plays), red_zone_share(plays),
                  first_read_share(plays), ball_quality(plays), rushing, snap_share(snaps)]:
        table = table.merge(stats, on=["team", "player_id"], how="left")

    # Players with no targets (or no carries) get 0 instead of an empty value
    counts = ["targets", "receptions", "target_share", "air_yards", "air_yards_share", "rz_targets",
              "rz_target_share", "first_read_targets", "first_read_share",
              "catchable_targets", "contested_targets", "drops",
              "carries", "rush_share", "goal_line_carries", "snaps", "snap_share"]
    table[counts] = table[counts].fillna(0)
    table["adot"] = table["air_yards"] / table["targets"].where(table["targets"] > 0)

    table = table.merge(scoring_stats(plays), on=["team", "player_id"], how="left")
    table[SCORING_STATS] = table[SCORING_STATS].fillna(0)
    table["ppr_points"] = score(table)
    table = add_expected_points(table)
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
    snaps = load_snaps(players)
    table = build_table(plays, players, snaps)
    print(f"Weeks included: {plays['week'].min()}-{plays['week'].max()}\n")

    shown = table[["player", "team", "position", "targets", "target_share",
                   "first_read_share", "snap_share", "ppr_points"]].head(20)
    print(shown.round(3).to_string(index=False))
