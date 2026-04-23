from fastapi import APIRouter, Query
import feedparser
import httpx
from datetime import datetime
import re

router = APIRouter()

INDIAN_FEEDS = [
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "category": "India Markets",
    },
    {
        "name": "Moneycontrol Business",
        "url": "https://www.moneycontrol.com/rss/business.xml",
        "category": "India Business",
    },
    {
        "name": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "category": "India Markets",
    },
    {
        "name": "Livemint Economy",
        "url": "https://www.livemint.com/rss/economy",
        "category": "India Economy",
    },
    {
        "name": "Financial Express Markets",
        "url": "https://www.financialexpress.com/market/feed/",
        "category": "India Markets",
    },
]

GLOBAL_FEEDS = [
    {
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "category": "Global Business",
    },
    {
        "name": "Bloomberg Markets",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "category": "Global Markets",
    },
    {
        "name": "CNBC Finance",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "category": "Global Finance",
    },
    {
        "name": "Financial Times",
        "url": "https://www.ft.com/?format=rss",
        "category": "Global Finance",
    },
]


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()[:300]


def parse_feed(feed_info: dict) -> list:
    """Parse a single RSS feed and return articles."""
    articles = []
    try:
        d = feedparser.parse(feed_info["url"])
        for entry in d.entries[:5]:
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            articles.append({
                "title": clean_html(getattr(entry, "title", "")),
                "summary": clean_html(getattr(entry, "summary", getattr(entry, "description", ""))),
                "link": getattr(entry, "link", ""),
                "published": published,
                "source": feed_info["name"],
                "category": feed_info["category"],
            })
    except Exception:
        pass
    return articles


@router.get("/india")
def get_india_news(limit: int = Query(20, ge=1, le=50)):
    """Get Indian market and business news from multiple RSS sources."""
    all_articles = []
    for feed in INDIAN_FEEDS:
        articles = parse_feed(feed)
        all_articles.extend(articles)
    return all_articles[:limit]


@router.get("/world")
def get_world_news(limit: int = Query(20, ge=1, le=50)):
    """Get global financial and business news."""
    all_articles = []
    for feed in GLOBAL_FEEDS:
        articles = parse_feed(feed)
        all_articles.extend(articles)
    return all_articles[:limit]


@router.get("/all")
def get_all_news(limit: int = Query(30, ge=1, le=60)):
    """Get combined India + global news."""
    india = get_india_news(limit=limit // 2)
    world = get_world_news(limit=limit // 2)
    combined = []
    # Interleave
    max_len = max(len(india), len(world))
    for i in range(max_len):
        if i < len(india):
            combined.append(india[i])
        if i < len(world):
            combined.append(world[i])
    return combined[:limit]
