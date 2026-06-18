#!/usr/bin/env python3
"""
media_recs.py — Curated media recommendation feed via Claude API
Fetches Substack RSS feeds, filters for recommendation content, outputs output/media_recs.xml
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
    ("GriersonLeitch", "https://griersonleitch.substack.com/feed"),   # film recs
    ("TheReveal",      "https://thereveal.substack.com/feed"),         # books
    ("AnneHelen",      "https://annehelen.substack.com/feed"),         # TV and culture
]

MAX_PER_FEED = 10
BATCH_SIZE   = 30
OUTPUT_FILE  = "output/media_recs.xml"

HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://substack.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MEDIA_NS = "http://search.yahoo.com/mrss/"

ET.register_namespace("media", MEDIA_NS)

FILTER_PROMPT = """You are filtering a set of newsletter articles for a media recommendation feed.

INCLUDE:
- Articles that recommend specific films, books, shows, or games
- "If you liked X, try Y" framing
- Curated lists or ranked picks
- Thoughtful reviews with a clear recommendation

EXCLUDE:
- News, announcements, or trailers without a recommendation angle
- Pure criticism or analysis with no actionable recommendation
- Industry/business news (box office, streaming deals, etc.)

Return ONLY a JSON array with one object per article:
[{"id": 1, "decision": "INCLUDE", "reason": "one sentence reason"}, ...]"""


# --- FETCH ---
def clean(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(name, url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        articles = []
        for item in root.findall(".//item")[:MAX_PER_FEED]:
            title = clean(item.findtext("title") or "")
            desc  = clean(item.findtext("description") or "")[:300]
            link  = (item.findtext("link") or "").strip()
            if title:
                articles.append({"source": name, "title": title, "desc": desc, "link": link})

        print(f"  {name}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  {name}: failed ({e})")
        return []


# --- CLAUDE FILTER ---
def filter_articles(articles):
    client = Anthropic()
    kept   = []

    for i in range(0, len(articles), BATCH_SIZE):
        batch    = articles[i:i + BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. [{a['source']}] {a['title']}" + (f" — {a['desc']}" if a["desc"] else "")
            for j, a in enumerate(batch)
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": f"{FILTER_PROMPT}\n\nArticles:\n{numbered}"}],
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
            print(f"  Batch failed: {e}")

    return kept


# --- BUILD RSS ---
def build_rss(articles):
    rss     = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text       = "Media Recommendations"
    ET.SubElement(channel, "link").text        = "https://github.com/JustinLycklama/rss-digest"
    ET.SubElement(channel, "description").text = "Curated media recs from newsletters, filtered by Claude"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for a in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = f"[{a['source']}] {a['title']}"
        ET.SubElement(item, "link").text        = a["link"]
        ET.SubElement(item, "description").text = f"<p>{a['desc']}</p><p><em>{a.get('reason', '')}</em></p>"
        guid      = ET.SubElement(item, "guid")
        guid.text = hashlib.sha1(a["link"].encode()).hexdigest()
        guid.set("isPermaLink", "false")

    ET.ElementTree(rss).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\nWrote {len(articles)} articles to {OUTPUT_FILE}")


# --- MAIN ---
if __name__ == "__main__":
    print("Fetching Substack feeds...")
    all_articles = []
    for name, url in FEEDS:
        all_articles.extend(fetch_feed(name, url))

    print(f"\nTotal fetched: {len(all_articles)}")
    print("Filtering with Claude...")
    kept = filter_articles(all_articles)
    print(f"Kept: {len(kept)}")
    build_rss(kept)
