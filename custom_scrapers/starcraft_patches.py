#!/usr/bin/env python3
"""
starcraft_patches.py
Fetch StarCraft II news from Blizzard's API and produce starcraft_patches.xml
Requires: requests
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
import re

API_URL = "https://news.blizzard.com/en-us/api/news/starcraft-2?pageSize=20"
OUTPUT_FILE = "output/starcraft_patches.xml"

HEADERS = {"User-Agent": "StarCraftPatchesRSS/1.0"}

def clean_text(s: str) -> str:
    if not s:
        return ""
    text = unescape(s)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fix_image_url(url: str) -> str:
    """Fix protocol-relative URLs"""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url

def fetch_news():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()

    items = []
    content_items = data.get("feed", {}).get("contentItems", [])

    for entry in content_items:
        props = entry.get("properties", {})

        title = clean_text(props.get("title", ""))
        summary = clean_text(props.get("summary", ""))
        news_url = props.get("newsUrl", "")
        last_updated = props.get("lastUpdated", "")
        author = props.get("author", "Blizzard Entertainment")
        category = props.get("category", "")

        # Get thumbnail image
        static_asset = props.get("staticAsset", {})
        image_url = fix_image_url(static_asset.get("imageUrl", ""))

        # Use newsId as guid
        news_id = props.get("newsId", "")

        if not title or not news_url:
            continue

        items.append({
            "title": title,
            "link": news_url,
            "description": summary,
            "image": image_url,
            "guid": news_id,
            "pub_date": last_updated,
            "author": author,
            "category": category,
        })

    return items

def format_rfc822_date(iso_date: str) -> str:
    """Convert ISO date to RFC 822 format for RSS"""
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except ValueError:
        return ""

def build_rss(items):
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "StarCraft II News & Patches"
    ET.SubElement(channel, "link").text = "https://news.blizzard.com/en-us/feed/starcraft-2"
    ET.SubElement(channel, "description").text = "Latest StarCraft II news, patch notes, and updates from Blizzard"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it["title"]
        ET.SubElement(item, "link").text = it["link"]

        desc_text = it["description"]
        if it["category"]:
            desc_text = f"[{it['category']}] {desc_text}"
        ET.SubElement(item, "description").text = desc_text

        guid_el = ET.SubElement(item, "guid")
        guid_el.text = it["guid"]
        guid_el.set("isPermaLink", "false")

        if it["pub_date"]:
            ET.SubElement(item, "pubDate").text = format_rfc822_date(it["pub_date"])

        if it["author"]:
            ET.SubElement(item, "author").text = it["author"]

        if it.get("image"):
            mc = ET.SubElement(item, "{http://search.yahoo.com/mrss/}content")
            mc.set("url", it["image"])
            mc.set("type", "image/jpeg")
            ET.SubElement(item, "enclosure", url=it["image"], type="image/jpeg", length="0")

    tree = ET.ElementTree(rss)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {len(items)} items to {OUTPUT_FILE}")

if __name__ == "__main__":
    news = fetch_news()
    if not news:
        print("No news found — API structure might have changed.")
    build_rss(news)
