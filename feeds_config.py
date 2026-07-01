from dataclasses import dataclass, field
from sources.rss import RSSSource
from sources.reddit import RedditSource
from sources.custom.blizzard import BlizzardSource
from sources.custom.shambhala import ShambhalaSource


@dataclass
class Feed:
    name: str               # used for output filename and archive filename
    title: str              # RSS channel title
    description: str        # RSS channel description
    sources: list           # list of source objects
    filter_prompt: str | None = None  # None = no Claude filter, "NOTION" = load from Notion
    archive_days: int = 7


FEEDS = [
    Feed(
        name="news",
        title="Daily News Digest",
        description="Curated daily news, filtered by Claude",
        sources=[
            RSSSource("BBC",         "http://feeds.bbci.co.uk/news/world/rss.xml"),
            RSSSource("Guardian",    "https://www.theguardian.com/world/rss"),
            RSSSource("NYT",         "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
            RSSSource("CBCCanada",   "https://www.cbc.ca/cmlink/rss-canada"),
            RSSSource("NPRPolitics", "https://feeds.npr.org/1014/rss.xml"),
            RSSSource("Verge",       "https://www.theverge.com/rss/index.xml"),
            RSSSource("Ars",         "https://feeds.arstechnica.com/arstechnica/index"),
            RSSSource("CBCToronto",  "https://www.cbc.ca/cmlink/rss-canada-toronto"),
            RSSSource("Spacing",     "https://spacing.ca/toronto/feed/"),
        ],
        filter_prompt="NOTION",
        archive_days=7,
    ),
    Feed(
        name="toronto_events",
        title="Toronto Events",
        description="Toronto evening and weekend events — raves, parties, and city happenings",
        sources=[
            RedditSource("TorontoRaves"),
            RSSSource("BlogTO", "https://feeds.feedburner.com/torontoevents"),
        ],
        filter_prompt=(
            "Filter Toronto event listings using these rules:\n\n"
            "INCLUDE:\n"
            "- Evening events (starting 5pm or later on weekdays)\n"
            "- Weekend events (any time Saturday or Sunday)\n"
            "- Raves, DJ sets, club nights, music festivals, concerts\n"
            "- Arts, culture, food, and general city events that fall in the above time windows\n\n"
            "EXCLUDE:\n"
            "- Comedy shows and stand-up events\n"
            "- Daytime weekday events (before 5pm Monday–Friday)\n"
            "- Memes, gear questions, music releases, set recordings, and general discussion (from Reddit)\n"
            "- Posts without a specific date or venue"
        ),
        archive_days=30,
    ),
    Feed(
        name="starcraft",
        title="StarCraft II News & Patches",
        description="Latest StarCraft II news, patch notes, and updates from Blizzard",
        sources=[BlizzardSource()],
        filter_prompt=None,
        archive_days=30,
    ),
    Feed(
        name="shambhala",
        title="Shambhala Music Festival Blog",
        description="The latest Shambhala Music Festival news for the Farmily",
        sources=[ShambhalaSource()],
        filter_prompt=None,
        archive_days=90,
    ),
]
