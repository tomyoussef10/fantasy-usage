"""
League power rankings, built from this site's own stats.

1. Player value = points per game, blended 50/50 with expected points per game
   (so it rewards both production and usage). QBs use points per game only,
   since expected points only measures targets and carries.
2. Each fantasy team's best lineup is filled from its healthy players using the
   league's starting slots (QB, RB, WR, TE, FLEX, SUPER_FLEX).
3. Power score = total value of the starters, scaled so the best team is 100.
4. Every position group and starter slot is ranked against the other teams and
   given a letter grade.
"""

import pandas as pd

DEFAULT_LINEUP = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}
FLEX_POSITIONS = {"FLEX": ["RB", "WR", "TE"], "SUPER_FLEX": ["QB", "RB", "WR", "TE"]}
SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]


def player_values(league_table, weekly):
    """Value per game for every rostered player."""
    games = weekly.groupby("player_id")["week"].nunique().rename("games")
    players = (league_table.dropna(subset=["fantasy_team"])
               .groupby(["fantasy_team", "player_id"], as_index=False)
               .agg(player=("player", "first"), position=("position", "first"),
                    status=("status", "first"), fantasy_points=("fantasy_points", "sum"),
                    expected_points=("expected_points", "sum")))
    players = players.join(games, on="player_id")
    players = players[players["games"] > 0]

    per_game = players["fantasy_points"] / players["games"]
    expected_per_game = players["expected_points"] / players["games"]
    players["value"] = per_game.where(players["position"] == "QB",
                                      0.5 * per_game + 0.5 * expected_per_game.fillna(per_game))
    return players


def best_lineup(team_players, lineup):
    """Fill the starting slots with the team's best healthy players. Returns one row per slot."""
    healthy = team_players[team_players["status"] == "Active"].sort_values("value", ascending=False)
    used = set()
    starters = []
    for slot in SLOT_ORDER:
        allowed = FLEX_POSITIONS.get(slot, [slot])
        for number in range(1, lineup.get(slot, 0) + 1):
            options = healthy[healthy["position"].isin(allowed) & ~healthy["player_id"].isin(used)]
            name = f"{slot}{number}" if lineup.get(slot, 0) > 1 else slot
            if options.empty:
                starters.append({"slot": name, "player": "(empty)", "position": None, "value": 0.0})
                continue
            pick = options.iloc[0]
            used.add(pick["player_id"])
            starters.append({"slot": name, "player": pick["player"],
                             "position": pick["position"], "value": pick["value"]})
    return pd.DataFrame(starters)


def letter_grade(rank, teams):
    """Top of the league = A, bottom = F."""
    share = (rank - 1) / max(teams - 1, 1)
    for cutoff, grade in [(0.15, "A"), (0.35, "B"), (0.65, "C"), (0.85, "D")]:
        if share <= cutoff:
            return grade
    return "F"


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def power_rankings(league_table, weekly, lineup=None, values=None):
    """Returns (team rankings, every team's starters with slot ranks, position ranks).
    values: optional {player_id: value} to rank by instead of value per game."""
    lineup = lineup or DEFAULT_LINEUP
    players = player_values(league_table, weekly)
    if values is not None:   # e.g. this week's projections or rest-of-season projections
        players["value"] = players["player_id"].map(values).fillna(0.0)

    lineups = []
    for team, team_players in players.groupby("fantasy_team"):
        lineups.append(best_lineup(team_players, lineup).assign(fantasy_team=team))
    lineups = pd.concat(lineups, ignore_index=True)
    teams = lineups["fantasy_team"].nunique()

    # Team power score
    totals = lineups.groupby("fantasy_team")["value"].sum().sort_values(ascending=False)
    team_rankings = pd.DataFrame({
        "rank": range(1, len(totals) + 1),
        "fantasy_team": totals.index,
        "score": (100 * totals / totals.max()).round().astype(int).values,
    })

    # Each starter slot ranked against the same slot on other teams
    lineups["slot_rank"] = lineups.groupby("slot")["value"].rank(ascending=False, method="min")
    lineups["grade"] = [letter_grade(r, teams) for r in lineups["slot_rank"]]

    # Position groups (all starters at that position, including FLEX) ranked across teams
    # (empty slots have no position, so they only lower the team score)
    by_position = (lineups.dropna(subset=["position"])
                   .groupby(["fantasy_team", "position"])["value"].sum().reset_index())
    by_position["rank"] = by_position.groupby("position")["value"].rank(ascending=False,
                                                                        method="min")
    by_position["grade"] = [letter_grade(r, teams) for r in by_position["rank"]]
    return team_rankings, lineups, by_position
