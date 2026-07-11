from __future__ import annotations

from app.collectors.rss_collector import RSSCollector
from app.collectors.reddit_collector import RedditCollector
from app.collectors.github_collector import GitHubCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.arxiv_collector import ArxivCollector

COLLECTOR_MAP: dict[str, type] = {
    "rss": RSSCollector,
    "reddit": RedditCollector,
    "github": GitHubCollector,
    "hackernews": HackerNewsCollector,
    "arxiv": ArxivCollector,
}

try:
    from app.collectors.telegram_collector import TelegramCollector
    COLLECTOR_MAP["telegram"] = TelegramCollector
except Exception:
    pass

try:
    from app.collectors.twitter_collector import TwitterCollector
    COLLECTOR_MAP["twitter"] = TwitterCollector
except Exception:
    pass

try:
    from app.collectors.website_collector import WebsiteCollector
    COLLECTOR_MAP["website"] = WebsiteCollector
except Exception:
    pass
