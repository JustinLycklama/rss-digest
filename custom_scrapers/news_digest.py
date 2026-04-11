#!/usr/bin/env python3
"""
news_digest.py — Daily curated news feed via Claude API
Fetches RSS feeds, filters by significance, outputs output/news.xml

Reads filter context from Notion (NOTION_TOKEN env var) if available,
falls back to hardcoded defaults.
"""

import os
import re
import json
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
from anthropic import Anthropic

# --- CONFIG ---
FEEDS = [
    ("BBC",          "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Guardian",     "https://www.theguardian.com/world/rss"),
    ("AlJazeera",    "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Verge",        "https://www.theverge.com/rss/index.xml"),
    ("Ars",          "https://feeds.arstechnica.com/arstechnica/index"),
    ("CBCToronto",   "https://www.cbc.ca/cmlink/rss-canada-toronto"),
]

MAX_PER_FEED   = 30
BATCH_SIZE     = 40
OUTPUT_FILE    = "output/news.xml"
ARCHIVE_FILE   = "output/news_archive.json"
ARCHIVE_DAYS   = 7

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
FILTER_PAGE_ID = "33ba1339f88a81799204f8b0d4a1ca71"  # News Filter Memory page

HEADERS  = {"User-Agent": "NewsDigest/1.0"}
MEDIA_NS = "http://search.yahoo.com/mrss/"

ET.register_namespace("media", MEDIA_NS)


# --- NOTION FETCH ---
def fetch_notion_filter_context():
    if not NOTION_TOKEN:
        print("No NOTION_TOKEN set, using default filter context")
        return DEFAULT_FILTER_CONTEXT
    try:
        url = f"https://api.notion.com/v1/blocks/{FILTER_PAGE_ID}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        blocks = r.json().get("results", [])

        lines = []
        for block in blocks:
            btype = block.get("type")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text.strip():
                lines.append(text.strip())

        if lines:
            print("Loaded filter context from Notion")
            return "\n".join(lines)
    except Exception as e:
        print(f"Could not fetch Notion filter context: {e} — using defaults")

    return DEFAULT_FILTER_CONTEXT


DEFAULT_FILTER_CONTEXT = """
The user wants a daily digest of significant world news. Apply these rules:

INCLUDE:
- Wars: escalation, de-escalation, major battles, peace deals
- Regime changes: elections with major outcomes, coups, leaders captured/killed
- Major economic policy: tariffs with significant global impact, market crashes, major sanctions
- Space launches and milestones
- Major tech product launches or significant company events (not funding rounds or layoffs)
- Natural disasters at large scale
- Major scientific breakthroughs

EXCLUDE:
- Day-to-day political back-and-forth
- Crime (unless a major world event)
- Celebrity, entertainment, sports
- Incremental follow-up stories unless something major changed
- Local news

SIGNIFICANCE TEST: Would this story still matter in a week? If no, exclude it.
"""


# --- RSS FETCH ---
def clean(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_image(item, ns=None):
    """Try to find an image URL from various RSS/Atom image fields."""
    # media:content or media:thumbnail
    for tag in [f"{{{MEDIA_NS}}}content", f"{{{MEDIA_NS}}}thumbnail"]:
        el = item.find(tag)
        if el is not None:
            url = el.attrib.get("url")
            if url:
                return url

    # enclosure
    enc = item.find("enclosure")
    if enc is not None and "image" in enc.attrib.get("type", ""):
        return enc.attrib.get("url")

    # <image> child
    img = item.find("image")
    if img is not None:
        url = img.findtext("url") or img.attrib.get("url")
        if url:
            return url

    # img tag inside description/content
    for field in ["description", "content"]:
        text = item.findtext(field) or ""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)

    return None


def fetch_feed(name, url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        items = []

        # RSS 2.0
        for item in root.findall(".//item")[:MAX_PER_FEED]:
            title = clean(item.findtext("title") or "")
            desc  = clean(item.findtext("description") or "")
            link  = (item.findtext("link") or "").strip()
            image = extract_image(item)
            if title:
                items.append({"source": name, "title": title, "desc": desc[:300], "link": link, "image": image})

        # Atom fallback
        if not items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:MAX_PER_FEED]:
                title   = clean(entry.findtext("atom:title", "", ns))
                summary = clean(entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or "")
                link_el = entry.find("atom:link", ns)
                link    = link_el.attrib.get("href", "") if link_el is not None else ""
                image   = extract_image(entry, ns)
                if title:
                    items.append({"source": name, "title": title, "desc": summary[:300], "link": link, "image": image})

        print(f"  {name}: {len(items)} articles")
        return items
    except Exception as e:
        print(f"  {name}: failed ({e})")
        return []


# --- DEDUP ---
def dedup(articles):
    """Remove near-duplicate articles based on first 6 words of title."""
    seen = {}
    out  = []
    for a in articles:
        key = " ".join(a["title"].lower().split()[:6])
        if key not in seen:
            seen[key] = True
            out.append(a)
    return out


# --- CLAUDE FILTER ---
def filter_articles(articles, filter_context):
    client = Anthropic()
    kept   = []

    for i in range(0, len(articles), BATCH_SIZE):
        batch    = articles[i:i + BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. [{a['source']}] {a['title']}" + (f" — {a['desc']}" if a["desc"] else "")
            for j, a in enumerate(batch)
        )

        prompt = f"""You are filtering a news feed for a single daily digest.

{filter_context}

Evaluate each article below. Return ONLY a JSON array with one object per article:
[{{"id": 1, "decision": "INCLUDE", "reason": "one sentence reason"}}, ...]

Articles:
{numbered}"""

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            decisions = json.loads(raw)

            for d in decisions:
                idx = d["id"] - 1
                if 0 <= idx < len(batch) and d["decision"] == "INCLUDE":
                    article = batch[idx].copy()
                    article["reason"] = d.get("reason", "")
                    kept.append(article)
                    print(f"  + {batch[idx]['title'][:70]}")

        except Exception as e:
            print(f"  Batch {i//BATCH_SIZE + 1} failed: {e}")
            continue

    return kept


# --- ARCHIVE ---
def load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        return []
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not load archive: {e} — starting fresh")
        return []


def save_archive(articles):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def merge_into_archive(archive, new_articles):
    """Add new articles to archive, dedup by guid, prune entries older than ARCHIVE_DAYS."""
    existing_guids = {a["guid"] for a in archive}
    now = datetime.now(UTC)

    for a in new_articles:
        guid = hashlib.sha1(a["link"].encode()).hexdigest()
        if guid not in existing_guids:
            a["guid"] = guid
            a["added_at"] = now.isoformat()
            archive.append(a)
            existing_guids.add(guid)

    cutoff = now.timestamp() - ARCHIVE_DAYS * 86400
    archive = [
        a for a in archive
        if datetime.fromisoformat(a["added_at"]).timestamp() > cutoff
    ]

    archive.sort(key=lambda a: a["added_at"], reverse=True)
    return archive


# --- BUILD RSS ---
def build_rss(articles):
    rss     = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text        = "Daily News Digest"
    ET.SubElement(channel, "link").text         = "https://github.com/JustinLycklama/rss-digest"
    ET.SubElement(channel, "description").text  = "Curated daily news, filtered by Claude"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for a in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = a["title"]
        ET.SubElement(item, "link").text        = a["link"]
        ET.SubElement(item, "description").text = f"<p>{a['desc']}</p><p><em>{a.get('reason', '')}</em></p>"
        guid      = ET.SubElement(item, "guid")
        guid.text = a.get("guid") or hashlib.sha1(a["link"].encode()).hexdigest()
        guid.set("isPermaLink", "false")

        if a.get("image"):
            mc = ET.SubElement(item, f"{{{MEDIA_NS}}}content")
            mc.set("url", a["image"])
            mc.set("medium", "image")

    ET.ElementTree(rss).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\nWrote {len(articles)} articles to {OUTPUT_FILE}")


# --- MAIN ---
if __name__ == "__main__":
    print("Fetching filter context...")
    filter_context = fetch_notion_filter_context()

    print("\nLoading archive...")
    archive = load_archive()
    archive_guids = {hashlib.sha1(a["link"].encode()).hexdigest() for a in archive}
    print(f"  {len(archive)} articles in archive")

    print("\nFetching feeds...")
    all_articles = []
    for name, url in FEEDS:
        all_articles.extend(fetch_feed(name, url))

    print(f"\nTotal fetched: {len(all_articles)}")
    all_articles = dedup(all_articles)
    # Skip articles already in archive — no need to re-filter them
    all_articles = [
        a for a in all_articles
        if hashlib.sha1(a["link"].encode()).hexdigest() not in archive_guids
    ]
    print(f"After dedup/archive filter: {len(all_articles)} new articles")

    print("\nFiltering with Claude...")
    kept = filter_articles(all_articles, filter_context)
    print(f"Kept:          {len(kept)} new articles")

    archive = merge_into_archive(archive, kept)
    save_archive(archive)
    print(f"Archive size:  {len(archive)} articles (rolling {ARCHIVE_DAYS} days)")

    build_rss(archive)
