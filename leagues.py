"""
Fantasy league syncing.

  - Sleeper: free, public, read-only API. Only a username is needed (no password).
    Docs: https://docs.sleeper.com
  - ESPN: unofficial API that ESPN's own site uses. Works for PUBLIC leagues only.
    Private leagues need the owner's login cookies, which a public website should never ask for.

The roster functions return (rosters, lineup):
  - rosters: one row per rostered player (fantasy_team, sleeper_id or espn_id), so the
    website can match league rosters to its own stats
  - lineup: the league's starting slots, like {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1}
"""

import json
import urllib.error
import urllib.request

import pandas as pd

SLEEPER = "https://api.sleeper.app/v1"
ESPN = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"


class LeagueError(Exception):
    """A problem we can explain to the visitor (wrong username, private league, ...)."""


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "fantasy-usage-stats"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise LeagueError("This league is private. Only public leagues can be synced.")
        if error.code == 404:
            raise LeagueError("League not found. Check the league ID.")
        raise LeagueError(f"The fantasy site returned an error ({error.code}). Try again later.")
    except Exception:
        raise LeagueError("Couldn't reach the fantasy site. Try again in a minute.")


# ---------- Sleeper ----------

def sleeper_leagues(username, season):
    """All of a Sleeper user's NFL leagues for one season, as {league name: league id}."""
    user = get_json(f"{SLEEPER}/user/{username.strip()}")
    if not user:
        raise LeagueError(f"No Sleeper user named '{username}'.")
    leagues = get_json(f"{SLEEPER}/user/{user['user_id']}/leagues/nfl/{season}") or []
    return {league["name"]: league["league_id"] for league in leagues}


def sleeper_rosters(league_id):
    """Every rostered player in a Sleeper league, with the fantasy team that has him."""
    league = get_json(f"{SLEEPER}/league/{league_id}") or {}
    lineup = {}
    for slot in league.get("roster_positions") or []:
        if slot in ("QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"):
            lineup[slot] = lineup.get(slot, 0) + 1

    users = get_json(f"{SLEEPER}/league/{league_id}/users") or []
    rosters = get_json(f"{SLEEPER}/league/{league_id}/rosters") or []

    team_names = {}
    for user in users:
        team_name = (user.get("metadata") or {}).get("team_name")
        team_names[user["user_id"]] = team_name or user.get("display_name") or "Unknown"

    rows = []
    for roster in rosters:
        team = team_names.get(roster.get("owner_id"), f"Team {roster.get('roster_id')}")
        for player_id in roster.get("players") or []:
            rows.append({"fantasy_team": team, "sleeper_id": str(player_id)})
    return pd.DataFrame(rows, columns=["fantasy_team", "sleeper_id"]), lineup or None


# ---------- ESPN ----------

def espn_rosters(league_id, season):
    """Every rostered player in a PUBLIC ESPN league, with the fantasy team that has him."""
    league_id = str(league_id).strip()
    data = get_json(f"{ESPN}/seasons/{season}/segments/0/leagues/{league_id}"
                    "?view=mTeam&view=mRoster&view=mSettings")

    rows = []
    for team in data.get("teams", []):
        # ESPN has used both "name" and "location" + "nickname" for team names
        name = team.get("name") or f"{team.get('location', '')} {team.get('nickname', '')}".strip()
        name = name or f"Team {team.get('id')}"
        for entry in (team.get("roster") or {}).get("entries", []):
            rows.append({"fantasy_team": name, "espn_id": str(entry.get("playerId"))})
    if not rows:
        raise LeagueError("No rosters found. The league may be private or not drafted yet.")

    # ESPN numbers its lineup slots: 0 = QB, 2 = RB, 4 = WR, 6 = TE, 23 = FLEX, 7 = superflex
    espn_slots = {"0": "QB", "2": "RB", "4": "WR", "6": "TE", "23": "FLEX", "7": "SUPER_FLEX"}
    counts = (data.get("settings", {}).get("rosterSettings", {}).get("lineupSlotCounts") or {})
    lineup = {espn_slots[k]: int(v) for k, v in counts.items() if k in espn_slots and int(v) > 0}
    return pd.DataFrame(rows, columns=["fantasy_team", "espn_id"]), lineup or None
