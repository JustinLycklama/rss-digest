import re
import time
import hashlib
import cloudscraper
import xml.etree.ElementTree as ET
from html import unescape
from email.utils import parsedate_to_datetime
from datetime import timezone

MEDIA_NS   = "http://search.yahoo.com/mrss/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

_scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)


def _parse_date(text):
    """Parse RFC 822, ISO 8601, or informal date strings → RFC 822 string, or '' on failure."""
    if not text:
        return ""
    from datetime import datetime
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        pass
    # Handle informal format: "Mon, Jan 5 2024" (Three Word Phrase)
    for fmt in ("%a, %b %d %Y", "%b %d %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pass
    return ""


def _clean(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_image(item):
    for tag in [f"{{{MEDIA_NS}}}content", f"{{{MEDIA_NS}}}thumbnail"]:
        el = item.find(tag)
        if el is not None and el.attrib.get("url"):
            return el.attrib["url"]
    enc = item.find("enclosure")
    if enc is not None and "image" in enc.attrib.get("type", ""):
        return enc.attrib.get("url")
    img = item.find("image")
    if img is not None:
        url = img.findtext("url") or img.attrib.get("url")
        if url:
            return url
    for field in ["description", "content", f"{{{CONTENT_NS}}}encoded"]:
        text = item.findtext(field) or ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
    return None


def _fetch_page_image(url):
    """Fetch a linked page and extract the first meaningful image."""
    try:
        r = _scraper.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', r.text)
        return match.group(1) if match else None
    except Exception:
        return None


class RSSSource:
    def __init__(self, name: str, url: str, max_items: int = 30,
                 fallback_image: str = None, fetch_page_image: bool = False):
        self.name = name
        self.url = url
        self.max_items = max_items
        self.fallback_image = fallback_image
        self.fetch_page_image = fetch_page_image

    def fetch(self) -> list[dict]:
        try:
            last_err = None
            for attempt in range(3):
                try:
                    r = _scraper.get(self.url, headers=HEADERS, timeout=15)
                    r.raise_for_status()
                    break
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        time.sleep(3)
            else:
                raise last_err
            content = r.content
            # Some feeds use media: prefix without declaring xmlns:media
            if b"media:" in content and b"xmlns:media" not in content:
                content = re.sub(
                    rb"(<(?:rss|feed)[^>]*)",
                    rb'\1 xmlns:media="http://search.yahoo.com/mrss/"',
                    content, count=1,
                )
            root = ET.fromstring(content)
            items = []

            for item in root.findall(".//item")[:self.max_items]:
                title = _clean(item.findtext("title") or "")
                desc  = _clean(item.findtext("description") or "")
                link  = (item.findtext("link") or "").strip()
                if not title:
                    title = self.name
                if link:
                    image = _extract_image(item) or self.fallback_image
                    if not image and self.fetch_page_image:
                        image = _fetch_page_image(link)
                    items.append({
                        "guid":     hashlib.sha1(link.encode()).hexdigest(),
                        "source":   self.name,
                        "title":    title,
                        "desc":     desc[:300],
                        "link":     link,
                        "image":    image,
                        "pub_date": _parse_date(item.findtext("pubDate") or ""),
                    })

            if not items:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns)[:self.max_items]:
                    title   = _clean(entry.findtext("atom:title", "", ns))
                    summary = _clean(entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or "")
                    link_el = entry.find("atom:link", ns)
                    link    = link_el.attrib.get("href", "") if link_el is not None else ""
                    if title:
                        atom_date = (
                            entry.findtext("atom:published", "", ns)
                            or entry.findtext("atom:updated", "", ns)
                        )
                        items.append({
                            "guid":     hashlib.sha1(link.encode()).hexdigest(),
                            "source":   self.name,
                            "title":    title,
                            "desc":     summary[:300],
                            "link":     link,
                            "image":    _extract_image(entry) or self.fallback_image,
                            "pub_date": _parse_date(atom_date),
                        })

            print(f"  {self.name}: {len(items)} articles")
            return items
        except Exception as e:
            print(f"  {self.name}: failed ({e})")
            return []
