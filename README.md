# Fantasy Usage Stats

A fantasy football website that shows advanced usage stats for every WR, TE, and RB, calculated from free NFL play-by-play data.

**Live site: [fantasy-usage.streamlit.app](https://fantasy-usage.streamlit.app)**

Built with Python, pandas, and Streamlit.

## Stats

| Stat | What it means |
| --- | --- |
| Snap share | Share of the team's offensive snaps the player was on the field for |
| Target share | Share of the team's targets thrown to the player |
| First-read share | Share of the team's first-read targets: throws to the first receiver the QB looked at |
| Air yards share | Share of the team's downfield passing yards aimed at the player |
| aDOT | Average depth of target: how far downfield the player is usually targeted |
| RZ target share | Share of the team's targets inside the opponent's 20-yard line |
| Catchable / contested / drops | Targets charted as catchable, contested, or dropped |
| Carries and rush share | Running plays and the player's share of the team's carries |
| GL carries | Carries inside the opponent's 5-yard line |
| Fantasy points | PPR, half PPR, or standard, chosen in the sidebar |
| Status | Current roster status (Active, Injured reserve, ...) from nflverse weekly rosters. Injured reserve players are marked with ⚠️; released, retired, and practice-squad players are left off the buy low list |
| Expected points | What a player's usage is usually worth, from a least-squares regression of PPR points on targets, air yards, red zone targets, carries, and goal-line carries |

The site opens with the latest NFL headlines, then has four tabs: **Receivers**, **Running backs**, **Buy low** (players scoring below or above what their usage predicts), and **Player search**, where you can look up any player and see weekly bar charts. Filter by week range and team in the sidebar.

## Out for the season

The free data can't tell a short injured reserve stint from a season-ending injury, so `out_for_season.txt` holds a hand-kept list of players ruled out for the year. They're removed from the Buy low list and marked "Out for season" everywhere else. Add a name when the news says a player is done for the season.

## How it works

- `phase1.py` loads the data and calculates each stat. Each play is one row, and stats come from filtering plays and grouping them by player and team.
- `news.py` reads free RSS feeds: RotoWire fantasy player news, Pro Football Rumors injuries and transactions, and ESPN NFL headlines, each linking to the full story.
- `app.py` builds the website: sidebar filters, the three tabs, tables, and charts.

Fantasy points match nflverse's official PPR totals for 99% of players.

## Run it yourself

```
pip install -r requirements.txt
streamlit run app.py
```

## Data

Play-by-play and snap count data from [nflverse](https://github.com/nflverse/nflverse-data). News from RotoWire, Pro Football Rumors, and ESPN RSS feeds. Player photos and bios from nflverse weekly rosters (photos hosted by the NFL). Charting data (first reads, drops, contested and catchable balls) from FTN Data via nflverse, used under the CC-BY-SA 4.0 license.
