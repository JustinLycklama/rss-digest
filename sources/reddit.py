import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from html import unescape

HEADERS = {"User-Agent": "python:rss-digest:v1.0 (by /u/frownigami)"}


def _clean(html_text):
    if not html_text:
        return ""
    text = unescape(html_text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


class RedditSource:
    def __init__(self, subreddit: str, max_items: int = 25):
        self.subreddit = subreddit
        self.max_items = max_items

    def fetch(self) -> list[dict]:
        url = f"https://www.reddit.com/r/{self.subreddit}/.rss?limit={self.max_items}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = []

            for entry in root.findall("atom:entry", ns):
                title   = _clean(entry.findtext("atom:title", "", ns))
                link_el = entry.find("atom:link", ns)
                link    = link_el.attrib.get("href", "") if link_el is not None else ""
                content = entry.find("atom:content", ns)
                desc    = _clean(content.text if content is not None else "")[:300]

                image = None
                thumb = entry.find("{http://search.yahoo.com/mrss/}thumbnail")
                if thumb is not None:
                    image = thumb.attrib.get("url")
                elif content is not None and content.text and 'img src="' in content.text:
                    match = re.search(r'<img src="([^"]+)"', content.text)
                    if match:
                        image = match.group(1)

                if title:
                    items.append({
                        "guid":     hashlib.sha1(link.encode()).hexdigest(),
                        "source":   f"r/{self.subreddit}",
                        "title":    title,
                        "desc":     desc,
                        "link":     link,
                        "image":    image,
                        "pub_date": "",
                    })

            print(f"  r/{self.subreddit}: {len(items)} posts")
            return items
        except Exception as e:
            print(f"  r/{self.subreddit}: failed ({e})")
            return []
