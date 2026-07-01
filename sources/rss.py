import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from html import unescape

MEDIA_NS = "http://search.yahoo.com/mrss/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


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
    for field in ["description", "content"]:
        text = item.findtext(field) or ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
    return None


class RSSSource:
    def __init__(self, name: str, url: str, max_items: int = 30):
        self.name = name
        self.url = url
        self.max_items = max_items

    def fetch(self) -> list[dict]:
        try:
            r = requests.get(self.url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = []

            for item in root.findall(".//item")[:self.max_items]:
                title = _clean(item.findtext("title") or "")
                desc  = _clean(item.findtext("description") or "")
                link  = (item.findtext("link") or "").strip()
                if title:
                    items.append({
                        "guid":     hashlib.sha1(link.encode()).hexdigest(),
                        "source":   self.name,
                        "title":    title,
                        "desc":     desc[:300],
                        "link":     link,
                        "image":    _extract_image(item),
                        "pub_date": "",
                    })

            if not items:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns)[:self.max_items]:
                    title   = _clean(entry.findtext("atom:title", "", ns))
                    summary = _clean(entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or "")
                    link_el = entry.find("atom:link", ns)
                    link    = link_el.attrib.get("href", "") if link_el is not None else ""
                    if title:
                        items.append({
                            "guid":     hashlib.sha1(link.encode()).hexdigest(),
                            "source":   self.name,
                            "title":    title,
                            "desc":     summary[:300],
                            "link":     link,
                            "image":    _extract_image(entry),
                            "pub_date": "",
                        })

            print(f"  {self.name}: {len(items)} articles")
            return items
        except Exception as e:
            print(f"  {self.name}: failed ({e})")
            return []
