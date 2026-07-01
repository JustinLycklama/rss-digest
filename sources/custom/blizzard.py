import re
import requests
from datetime import datetime, UTC
from html import unescape

API_URL = "https://news.blizzard.com/en-us/api/news/starcraft-2?pageSize=20"
HEADERS = {"User-Agent": "StarCraftPatchesRSS/1.0"}


def _clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", unescape(s)).strip()


def _fix_url(url):
    if url and url.startswith("//"):
        return "https:" + url
    return url or ""


def _rfc822(iso_date):
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except ValueError:
        return ""


class BlizzardSource:
    def fetch(self) -> list[dict]:
        try:
            r = requests.get(API_URL, headers=HEADERS, timeout=20)
            r.raise_for_status()
            items = []
            for entry in r.json().get("feed", {}).get("contentItems", []):
                props = entry.get("properties", {})
                title = _clean(props.get("title", ""))
                link  = props.get("newsUrl", "")
                if not title or not link:
                    continue
                category = props.get("category", "")
                desc = _clean(props.get("summary", ""))
                if category:
                    desc = f"[{category}] {desc}"
                items.append({
                    "guid":     props.get("newsId", ""),
                    "source":   "Blizzard",
                    "title":    title,
                    "desc":     desc,
                    "link":     link,
                    "image":    _fix_url(props.get("staticAsset", {}).get("imageUrl", "")),
                    "pub_date": _rfc822(props.get("lastUpdated", "")),
                })
            print(f"  Blizzard: {len(items)} items")
            return items
        except Exception as e:
            print(f"  Blizzard: failed ({e})")
            return []
