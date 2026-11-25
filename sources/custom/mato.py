import json
import re
import hashlib
import requests
from datetime import datetime, timezone, timedelta

BASE_URL   = "https://ma.to"
CITY_URLS  = [
    f"{BASE_URL}/events/toronto",
    f"{BASE_URL}/events/toronto/next-week",
]
MIN_DAYS_AHEAD = 5
HEADERS  = {"User-Agent": "MatoRSS/1.0"}


def _extract_json_ld(html, type_filter=None):
    for m in re.finditer(r'<script type="application/ld\+json">([\s\S]*?)</script>', html):
        try:
            data = json.loads(m.group(1))
            if type_filter is None or data.get("@type") == type_filter:
                return data
        except Exception:
            continue
    return None


def _rfc822(iso_date):
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date)
        return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return ""


def _format_desc(event):
    desc = event.get("description", "")
    location = event.get("location", {})
    venue = location.get("name", "")
    address = location.get("address", {}).get("streetAddress", "")
    start = event.get("startDate", "")
    if start:
        try:
            dt = datetime.fromisoformat(start)
            start_str = dt.strftime("%a %b %-d, %Y · %-I:%M %p")
        except Exception:
            start_str = start
    else:
        start_str = ""
    parts = []
    if venue:
        parts.append(f"<strong>{venue}</strong>" + (f" — {address}" if address else ""))
    if start_str:
        parts.append(start_str)
    if desc:
        parts.append(desc)
    return "<br>".join(parts)


def _get_event_list(html):
    for m in re.finditer(r'<script type="application/ld\+json">([\s\S]*?)</script>', html):
        try:
            data = json.loads(m.group(1))
            for node in data.get("@graph", []):
                if node.get("@type") == "CollectionPage":
                    return node.get("mainEntity", {}).get("itemListElement", [])
        except Exception:
            continue
    return []


class MatoSource:
    name = "MATO"

    def fetch(self) -> list[dict]:
        try:
            seen_urls = set()
            event_list = []
            for city_url in CITY_URLS:
                r = requests.get(city_url, headers=HEADERS, timeout=20)
                r.raise_for_status()
                for entry in _get_event_list(r.text):
                    url = entry.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        event_list.append(entry)

            if not event_list:
                print("  MATO: no events found")
                return []

            cutoff = datetime.now(timezone.utc) + timedelta(days=MIN_DAYS_AHEAD)
            items = []
            for entry in event_list:
                url = entry.get("url", "")
                name = entry.get("name", "")
                if not url or not name:
                    continue

                try:
                    er = requests.get(url, headers=HEADERS, timeout=15)
                    er.raise_for_status()
                    event = _extract_json_ld(er.text, type_filter="Event")
                except Exception as e:
                    print(f"  MATO: failed to fetch {url} ({e})")
                    continue

                if not event:
                    continue

                start_date = event.get("startDate", "")
                if start_date:
                    try:
                        if datetime.fromisoformat(start_date).astimezone(timezone.utc) < cutoff:
                            continue
                    except Exception:
                        pass

                image = event.get("image", "")
                if isinstance(image, list):
                    image = image[0] if image else ""

                guid = hashlib.sha1(url.encode()).hexdigest()
                items.append({
                    "guid":     guid,
                    "source":   "MATO",
                    "title":    event.get("name", name),
                    "desc":     _format_desc(event),
                    "link":     url,
                    "image":    image,
                    "pub_date": _rfc822(start_date),
                })

            print(f"  MATO: {len(items)} events")
            return items

        except Exception as e:
            print(f"  MATO: failed ({e})")
            return []
