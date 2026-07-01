import re
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from html import unescape

URL      = "https://www.shambhalamusicfestival.com/blog"
BASE_URL = "https://www.shambhalamusicfestival.com"
HEADERS  = {"User-Agent": "ShambhalaRSS/1.0"}


def _clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", unescape(s)).strip()


def _rfc822(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%a, %d %b %Y 00:00:00 +0000")
    except ValueError:
        return ""


class ShambhalaSource:
    def fetch(self) -> list[dict]:
        try:
            r = requests.get(URL, headers=HEADERS, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            items = []
            seen = set()

            for div in soup.find_all("div", class_="w-dyn-item"):
                link_el = div.find("a", href=re.compile(r"^/blog/"))
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)
                link = BASE_URL + href

                title_el = div.find(["h3", "h4"])
                title = _clean(title_el.get_text()) if title_el else ""
                if not title:
                    continue

                desc_el = div.find("div", class_="text-size-regular")
                desc = _clean(desc_el.get_text()) if desc_el else ""

                cat_link = div.find("a", href=re.compile(r"^/category/"))
                category = ""
                if cat_link:
                    cat_div = cat_link.find("div", class_="text-size-small")
                    if cat_div:
                        category = _clean(cat_div.get_text())
                if category:
                    desc = f"[{category}] {desc}"

                date_str = ""
                for d in div.find_all("div", class_="text-size-small"):
                    text = d.get_text(strip=True)
                    if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", text):
                        date_str = text
                        break

                image = ""
                img_el = div.find("img", class_=re.compile(r"blog"))
                if img_el:
                    srcset = img_el.get("srcset", "")
                    if srcset:
                        parts = srcset.split(",")
                        if parts:
                            image = parts[-1].strip().split(" ")[0]
                    if not image:
                        image = img_el.get("src", "")

                guid = hashlib.sha1((title + link).encode()).hexdigest()
                items.append({
                    "guid":     guid,
                    "source":   "Shambhala",
                    "title":    title,
                    "desc":     desc,
                    "link":     link,
                    "image":    image,
                    "pub_date": _rfc822(date_str),
                })

            print(f"  Shambhala: {len(items)} posts")
            return items
        except Exception as e:
            print(f"  Shambhala: failed ({e})")
            return []
