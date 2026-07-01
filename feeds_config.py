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
        name="toronto_raves",
        title="Toronto Raves",
        description="Upcoming Toronto rave and club events from r/TorontoRaves",
        sources=[
            RedditSource("TorontoRaves"),
        ],
        filter_prompt=(
            "Only include posts that are announcing or advertising an upcoming event — "
            "a rave, party, DJ set, or club night with a specific date or venue.\n"
            "EXCLUDE: posts looking for people to attend with, recommendation requests, "
            "general discussion, gear questions, music releases, and set recordings."
        ),
        archive_days=30,
    ),
    Feed(
        name="toronto_events",
        title="Toronto Events",
        description="Toronto evening and weekend events from BlogTO and Now Toronto",
        sources=[
            RSSSource("BlogTO",     "https://www.blogto.com/rss/events.xml"),
            RSSSource("NowToronto", "https://nowtoronto.com/events/feed/"),
        ],
        filter_prompt=(
            "Include Toronto events that are:\n"
            "- Evening events (5pm or later on weekdays)\n"
            "- Weekend events (any time Saturday or Sunday)\n"
            "- Raves, DJ sets, concerts, arts, culture, and food events\n\n"
            "EXCLUDE:\n"
            "- Comedy shows and stand-up events\n"
            "- Daytime weekday events (before 5pm Monday–Friday)\n"
            "- Events without a specific date or venue\n\n"
            "PRIORITIZATION: The user lives near Trinity Bellwoods in Toronto's west end. "
            "Rank higher events in or near: Trinity-Bellwoods, Dufferin Grove, Little Portugal, "
            "Roncesvalles, Palmerston-Little Italy, West Queen West, South Parkdale, "
            "Kensington-Chinatown, Junction, High Park, Corso Italia, Wychwood, Dovercourt, "
            "Fort York, Liberty Village."
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
