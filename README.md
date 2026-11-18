# Fantasy Usage Stats

A fantasy football website that shows advanced usage stats for every WR, TE, and RB, calculated from free NFL play-by-play data.

**Live site: [fantasy-usage.streamlit.app](https://fantasy-usage.streamlit.app)**

Built with Python, pandas, and Streamlit.

## Stats

| Stat | What it means |
| --- | --- |
| Target share | Share of the team's targets thrown to the player |
| Air yards share | Share of the team's downfield passing yards aimed at the player |
| aDOT | Average depth of target: how far downfield the player is usually targeted |
| RZ target share | Share of the team's targets inside the opponent's 20-yard line, where most touchdowns happen |
| PPR points | Fantasy points in PPR scoring |

Filter by position, team, and minimum targets, and sort any column.

## How it works

- `phase1.py` loads every play of the season and calculates each stat. Each play is one row, and stats come from filtering plays and grouping them by player and team.
- `app.py` builds the website: filters, the stats table, and formatting.

Fantasy points match nflverse's official PPR totals for 99% of players.

## Run it yourself

```
pip install -r requirements.txt
streamlit run app.py
```

## Data

Play-by-play data from [nflverse](https://github.com/nflverse/nflverse-data).
