"""
NFL news headlines from free RSS feeds.

RSS is a free, public format that news sites use to share their latest headlines.
We show each headline with a link to the full story on the original site.
"""

import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

FEEDS = {
    "ESPN": "https://www.espn.com/espn/rss/nfl/news",
}


def get_headlines(limit=8):
    """Return the newest headlines as a list of {title, link, source, published}.
    If a feed can't be reached, it's skipped instead of crashing the site."""
    headlines = []
    for source, url in FEEDS.items():
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "fantasy-usage-stats"})
            with urllib.request.urlopen(request, timeout=10) as response:
                root = ET.fromstring(response.read())
        except Exception:
            continue

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            date_text = item.findtext("pubDate")
            try:
                published = parsedate_to_datetime(date_text) if date_text else None
            except (TypeError, ValueError):
                published = None
            if title and link:
                headlines.append({"title": title, "link": link,
                                  "source": source, "published": published})

    headlines.sort(key=lambda h: h["published"].timestamp() if h["published"] else 0,
                   reverse=True)
    return headlines[:limit]
