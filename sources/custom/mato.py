import json
import re
import hashlib
import requests
from datetime import datetime, timezone

BASE_URL = "https://ma.to"
CITY_URL = f"{BASE_URL}/events/toronto"
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


class MatoSource:
    def fetch(self) -> list[dict]:
        try:
            r = requests.get(CITY_URL, headers=HEADERS, timeout=20)
            r.raise_for_status()

            collection = None
            for m in re.finditer(r'<script type="application/ld\+json">([\s\S]*?)</script>', r.text):
                try:
                    data = json.loads(m.group(1))
                    for node in data.get("@graph", []):
                        if node.get("@type") == "CollectionPage":
                            collection = node
                            break
                except Exception:
                    continue
                if collection:
                    break
            if not collection:
                print("  MATO: could not find CollectionPage in JSON-LD")
                return []

            event_list = collection.get("mainEntity", {}).get("itemListElement", [])
            if not event_list:
                print("  MATO: no events in listing")
                return []

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

                image = event.get("image", "")
                # image may be a list
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
                    "pub_date": _rfc822(event.get("startDate", "")),
                })

            print(f"  MATO: {len(items)} events")
            return items

        except Exception as e:
            print(f"  MATO: failed ({e})")
            return []
