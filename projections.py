"""
Fantasy projections, built from this site's own stats.

Projection for one game =
    baseline     (how good the player has been: recent games weighted more than the
                  whole season, half actual points and half expected points from usage)
  x matchup      (how many points the opposing defense allows to his position,
                  compared with the league average)
  x environment  (the team's Vegas implied points this week, compared with how many
                  points the team usually scores)
  x shadow       (lower if a top cornerback is expected to shadow him; hand-kept list)

The matchup and environment effects are shrunk halfway toward "average", because
a defense's numbers from 9 or 10 games are noisy.
"""

import numpy as np
import pandas as pd

USAGE_COLUMNS = ["targets", "air_yards", "rz_targets", "carries", "goal_line_carries"]
RECENT_GAMES = 4
SHADOW_PENALTY = 0.85        # a shadowed receiver keeps 85% of his projection


def opponents(schedule):
    """One row per team per week: who they play, at home or away, and Vegas implied points.
    nflverse's spread_line is home points minus away points, so
    home implied = (total + spread) / 2 and away implied = (total - spread) / 2."""
    home = pd.DataFrame({"week": schedule["week"], "team": schedule["home_team"],
                         "opponent": schedule["away_team"],
                         "implied": (schedule["total_line"] + schedule["spread_line"]) / 2})
    away = pd.DataFrame({"week": schedule["week"], "team": schedule["away_team"],
                         "opponent": schedule["home_team"],
                         "implied": (schedule["total_line"] - schedule["spread_line"]) / 2})
    return pd.concat([home, away], ignore_index=True)


def add_weekly_expected(weekly, season_table, points_column):
    """Expected points for each player-week, using values learned from the whole season."""
    fit = season_table[(season_table["position"] != "QB") &
                       ((season_table["targets"] + season_table["carries"]) >= 10)]
    values, *_ = np.linalg.lstsq(fit[USAGE_COLUMNS].to_numpy(float),
                                 fit[points_column].to_numpy(float), rcond=None)
    weekly = weekly.reset_index(drop=True)
    expected = pd.Series(weekly[USAGE_COLUMNS].to_numpy(float) @ values, index=weekly.index)
    # QBs score mostly from passing, which usage doesn't measure: use actual points
    weekly["expected"] = expected.where(weekly["position"] != "QB", weekly[points_column])
    return weekly


def baselines(weekly, points_column):
    """Points per game each player is expected to score in an average matchup."""
    games = weekly.groupby(["player_id", "week"], as_index=False).agg(
        points=(points_column, "sum"), expected=("expected", "sum"),
        team=("team", "last"), position=("position", "first"), player=("player", "first"),
        full_name=("full_name", "first"))
    games["blend"] = 0.5 * games["points"] + 0.5 * games["expected"]
    games = games.sort_values("week")

    season = games.groupby("player_id")["blend"].mean()
    recent = games.groupby("player_id")["blend"].apply(lambda b: b.tail(RECENT_GAMES).mean())
    info = games.groupby("player_id").agg(team=("team", "last"), position=("position", "first"),
                                          player=("player", "first"),
                                          full_name=("full_name", "first"),
                                          games=("week", "nunique"))
    info["baseline"] = 0.6 * recent + 0.4 * season
    return info.reset_index()


def matchup_ratings(weekly, schedule, points_column):
    """For each defense and position: points allowed per game / league average.
    1.2 means the defense gives up 20% more than average (a good matchup)."""
    games = opponents(schedule)
    scored = weekly.merge(games[["week", "team", "opponent"]], on=["week", "team"])
    allowed = (scored.groupby(["opponent", "position", "week"])[points_column].sum()
               .groupby(["opponent", "position"]).mean().rename("allowed").reset_index())
    league = allowed.groupby("position")["allowed"].mean().rename("league_avg")
    allowed = allowed.join(league, on="position")
    ratio = allowed["allowed"] / allowed["league_avg"]
    allowed["matchup"] = (1 + 0.5 * (ratio - 1)).clip(0.75, 1.25)   # shrink halfway to average
    return allowed.rename(columns={"opponent": "defense"})[["defense", "position", "matchup"]]


def team_scoring(plays):
    """Average points each team has scored per game."""
    finals = plays.sort_values("play_id").groupby("game_id").last()
    scored = pd.concat([
        pd.DataFrame({"team": finals["home_team"], "points": finals["total_home_score"]}),
        pd.DataFrame({"team": finals["away_team"], "points": finals["total_away_score"]}),
    ])
    return scored.groupby("team")["points"].mean().rename("avg_points")


def project(weekly, season_table, schedule, plays, points_column, week, shadows=None):
    """Projection for every player for one week (0 on a bye)."""
    weekly = add_weekly_expected(weekly, season_table, points_column)
    base = baselines(weekly, points_column)
    games = opponents(schedule)
    this_week = games[games["week"] == week]

    out = base.merge(this_week, on="team", how="left")
    out = out.merge(matchup_ratings(weekly, schedule, points_column),
                    left_on=["opponent", "position"], right_on=["defense", "position"],
                    how="left")
    out["matchup"] = out["matchup"].fillna(1.0)

    out = out.join(team_scoring(plays), on="team")
    environment = out["implied"] / out["avg_points"]
    out["environment"] = (1 + 0.5 * (environment - 1)).clip(0.8, 1.2).fillna(1.0)

    out["shadow"] = ""
    out["shadow_factor"] = 1.0
    for receiver, corner in (shadows or {}).items():
        hit = out["full_name"] == receiver
        out.loc[hit, "shadow"] = corner
        out.loc[hit, "shadow_factor"] = SHADOW_PENALTY

    out["projection"] = (out["baseline"] * out["matchup"] * out["environment"]
                         * out["shadow_factor"])
    out.loc[out["opponent"].isna(), "projection"] = 0.0    # bye week
    return out


def rest_of_season(weekly, season_table, schedule, plays, points_column, first_week,
                   last_week=18):
    """Projected points from first_week through the end of the regular season.
    Future weeks without Vegas lines use matchup only."""
    weekly_exp = add_weekly_expected(weekly, season_table, points_column)
    base = baselines(weekly_exp, points_column).set_index("player_id")
    ratings = matchup_ratings(weekly_exp, schedule, points_column)
    games = opponents(schedule)
    games = games[games["week"].between(first_week, last_week)]

    remaining = base[["team", "position", "baseline"]].reset_index().merge(games, on="team")
    remaining = remaining.merge(ratings, left_on=["opponent", "position"],
                                right_on=["defense", "position"], how="left")
    remaining["points"] = remaining["baseline"] * remaining["matchup"].fillna(1.0)
    totals = remaining.groupby("player_id").agg(ros_points=("points", "sum"),
                                                ros_games=("week", "nunique"))
    return totals.reset_index()
