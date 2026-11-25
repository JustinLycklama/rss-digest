import hashlib
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BASE_URL     = "https://monarchtavern.netlify.app"
SUPABASE_URL = "https://ffejqqqltnseiytktcmy.supabase.co"
REST_URL     = f"{SUPABASE_URL}/rest/v1/events"

# Publishable anon key shipped in the site's own JS bundle. Read-only, RLS-gated —
# this is the same key any visitor's browser uses to read the public events table.
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZmZWpxcXFsdG5zZWl5dGt0Y215Iiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3ODA0NjU5NjUsImV4cCI6MjA5NjA0MTk2NX0."
    "kVa5bmccbhkwgH5gO1WHCsnUsbaYbRtCmRnQIJY6JgQ"
)

# Weekly standing fixtures (karaoke night, resident DJ nights) are published as
# individual rows stretching months ahead — the venue's fixed schedule, not events
# to discover. Dropped at the source so they don't flood the feed (Principle 1).
EXCLUDE_SOURCES = {"recurring"}

# Events starting further out than this are skipped until they're closer, so the
# feed stays near-term and season-long fixtures (e.g. football) don't pile up.
MAX_DAYS_AHEAD = 90

VENUE_LABELS = {"downstairs": "Downstairs", "upstairs": "Upstairs"}
TZ = ZoneInfo("America/Toronto")
HEADERS = {
    "User-Agent": "MonarchRSS/1.0",
    "apikey": ANON_KEY,
    "Authorization": f"Bearer {ANON_KEY}",
}


def _rfc822(iso_utc):
    if not iso_utc:
        return ""
    try:
        return datetime.fromisoformat(iso_utc).astimezone(timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
    except Exception:
        return ""


def _format_desc(event):
    parts = []

    venue = VENUE_LABELS.get(event.get("venue") or "", "")
    start = event.get("start_at", "")
    when = ""
    if start:
        try:
            when = datetime.fromisoformat(start).astimezone(TZ).strftime(
                "%a %b %-d, %Y · %-I:%M %p"
            )
        except Exception:
            when = ""

    header = " · ".join(p for p in (venue, when) if p)
    if header:
        parts.append(f"<strong>{header}</strong>")

    desc = (event.get("description") or "").strip()
    if desc:
        parts.append(desc)

    ticket_url = event.get("ticket_url")
    if ticket_url:
        parts.append(f'<a href="{ticket_url}">Tickets</a>')

    return "<br>".join(parts)


class MonarchSource:
    name = "Monarch"

    def fetch(self) -> list[dict]:
        try:
            fmt = "%Y-%m-%dT%H:%M:%S"
            now_dt = datetime.now(timezone.utc)
            now = now_dt.strftime(fmt)
            cutoff = (now_dt + timedelta(days=MAX_DAYS_AHEAD)).strftime(fmt)
            r = requests.get(
                REST_URL,
                params={
                    "status": "eq.published",
                    "hide_from_calendar": "is.false",
                    "and": f"(start_at.gte.{now},start_at.lte.{cutoff})",
                    "order": "start_at.asc",
                    "select": (
                        "slug,title,start_at,venue,description,"
                        "image_urls,ticket_url,source"
                    ),
                },
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            events = r.json()

            items = []
            for event in events:
                if event.get("source") in EXCLUDE_SOURCES:
                    continue

                slug = event.get("slug")
                title = (event.get("title") or "").strip()
                if not slug or not title:
                    continue

                image = ""
                image_urls = event.get("image_urls") or []
                if isinstance(image_urls, list) and image_urls:
                    image = image_urls[0]

                link = event.get("ticket_url") or f"{BASE_URL}/?event={slug}"
                guid = hashlib.sha1(f"monarch:{slug}".encode()).hexdigest()

                items.append({
                    "guid":     guid,
                    "source":   "Monarch",
                    "title":    title,
                    "desc":     _format_desc(event),
                    "link":     link,
                    "image":    image,
                    "pub_date": _rfc822(event.get("start_at", "")),
                })

            print(f"  Monarch: {len(items)} events")
            return items

        except Exception as e:
            print(f"  Monarch: failed ({e})")
            return []
