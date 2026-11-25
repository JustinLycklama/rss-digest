import re
import hashlib
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = "https://sharpenskills.ca"
LISTINGS_API = f"{BASE_URL}/wp-json/affutes-acuity/v1/listings"
HEADERS = {"User-Agent": "SharpenRSS/1.0"}
MIN_DAYS_AHEAD = 3
MAX_PAGES = 5

# Rotate through one category per day. Term IDs from their WP taxonomy.
CATEGORIES = [
    (2820, "Cooking"),
    (52,   "Woodworking"),
    (49,   "Sewing"),
    (131,  "Crafts"),
    (127,  "Renovation/DIY"),
    (2946, "Decorative art"),
    (237,  "Knitting"),
    (1185, "Bicycle"),
    (2944, "Needle & Fabric"),
]


def _rfc822(dt_str):
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=-5)))  # EST
        return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return ""


def _parse_events(data_html):
    events = []
    for date_label, html_items in data_html.items():
        for html in html_items:
            datetime_m = re.search(r'data-class-datetime="([^"]+)"', html)
            title_link_m = re.search(
                r'class="workshop-title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>',
                html,
            )
            desc_m = re.search(
                r'<div[^>]*class="workshop-description"[^>]*>([\s\S]*?)</div>', html
            )
            img_m = re.search(r'<img[^>]*src="([^"]+)"', html)

            if not datetime_m or not title_link_m:
                continue

            dt_str = datetime_m.group(1)
            link = title_link_m.group(1)
            title = title_link_m.group(2).strip()
            desc = ""
            if desc_m:
                desc = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip()
                desc = re.sub(r"\s+", " ", desc)
            image = img_m.group(1) if img_m else ""

            events.append(
                {
                    "dt_str": dt_str,
                    "title": title,
                    "link": link,
                    "desc": desc,
                    "image": image,
                }
            )
    return events


class SharpenSkillsSource:
    name = "Sharpen"

    def fetch(self) -> list[dict]:
        try:
            day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
            term_id, category_name = CATEGORIES[day_of_year % len(CATEGORIES)]
            print(f"  SharpenSkills: today's category: {category_name} (term {term_id})")

            cutoff = datetime.now(timezone.utc) + timedelta(days=MIN_DAYS_AHEAD)
            seen_links = set()
            items = []

            for page_num in range(1, MAX_PAGES + 1):
                r = requests.get(
                    LISTINGS_API,
                    params={"mode": "chrono", "page_num": page_num, "how_many": 20,
                            "lang": "en", "category_terms": term_id},
                    headers=HEADERS,
                    timeout=20,
                )
                r.raise_for_status()
                payload = r.json()
                data = payload.get("data", {})
                data_html = data.get("data_html", {})

                for event in _parse_events(data_html):
                    link = event["link"]
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    dt_str = event["dt_str"]
                    try:
                        dt = datetime.fromisoformat(dt_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone(timedelta(hours=-5)))
                        if dt.astimezone(timezone.utc) < cutoff:
                            continue
                    except Exception:
                        pass

                    guid = hashlib.sha1(link.encode()).hexdigest()
                    items.append(
                        {
                            "guid": guid,
                            "source": f"Sharpen/{category_name}",
                            "title": event["title"],
                            "desc": event["desc"],
                            "link": link,
                            "image": event["image"],
                            "pub_date": _rfc822(dt_str),
                        }
                    )

                if not data.get("has_more_pages"):
                    break

            print(f"  SharpenSkills: {len(items)} {category_name} workshops")
            return items

        except Exception as e:
            print(f"  SharpenSkills: failed ({e})")
            return []
