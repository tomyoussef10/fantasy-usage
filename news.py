"""
NFL news from free RSS feeds.

RSS is a free, public format that news sites use to share their latest headlines.
We show each headline with a link to the full story on the original site.
  - RotoWire: short fantasy player updates (injuries, depth charts). RotoWire offers
    this feed for personal websites to use.
  - ESPN: NFL news articles.
"""

import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

FEEDS = {
    "RotoWire": "https://www.rotowire.com/rss/news.php?sport=NFL",
    "ESPN": "https://www.espn.com/espn/rss/nfl/news",
}


def get_headlines(source, limit=30):
    """Return the newest items from one feed as a list of {title, link, published}.
    Keeps the feed's own order (newest first). If the feed can't be reached,
    returns an empty list instead of crashing the site."""
    try:
        request = urllib.request.Request(FEEDS[source], headers={"User-Agent": "fantasy-usage-stats"})
        with urllib.request.urlopen(request, timeout=10) as response:
            root = ET.fromstring(response.read())
    except Exception:
        return []

    headlines = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date_text = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(date_text) if date_text else None
        except (TypeError, ValueError):
            published = None
        # Feeds use different time zones; convert to Eastern so times match the viewer's
        if published is not None and published.tzinfo is not None:
            published = published.astimezone(EASTERN)
        if title and link:
            headlines.append({"title": title, "link": link, "published": published})
    return headlines[:limit]
