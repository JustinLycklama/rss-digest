#!/usr/bin/env python3
"""
shambhala.py
Scrape https://www.shambhalamusicfestival.com/blog and produce shambhala.xml
Requires: requests, beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
import hashlib
import re

URL = "https://www.shambhalamusicfestival.com/blog"
BASE_URL = "https://www.shambhalamusicfestival.com"
OUTPUT_FILE = "output/shambhala.xml"

HEADERS = {"User-Agent": "ShambhalaRSS/1.0"}

def clean_text(s: str) -> str:
    if not s:
        return ""
    text = unescape(s)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def make_guid(title: str, link: str) -> str:
    h = hashlib.sha1()
    h.update((title + '||' + (link or "")).encode("utf-8"))
    return h.hexdigest()

def parse_date(date_str: str) -> str:
    """Parse date like 'October 14, 2025' to RFC 822 format"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%a, %d %b %Y 00:00:00 +0000")
    except ValueError:
        return ""

def scrape_blog():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen_links = set()

    # Find all blog item containers (both featured and regular)
    blog_items = soup.find_all('div', class_='w-dyn-item')

    for item_div in blog_items:
        # Find the link to the blog post
        link_el = item_div.find('a', href=re.compile(r'^/blog/'))
        if not link_el:
            continue

        href = link_el.get('href', '')
        if not href or href in seen_links:
            continue
        seen_links.add(href)

        full_link = BASE_URL + href

        # Find title (h3 or h4)
        title_el = item_div.find(['h3', 'h4'])
        title = clean_text(title_el.get_text()) if title_el else ""

        if not title:
            continue

        # Find image
        img_el = item_div.find('img', class_=re.compile(r'blog'))
        image_url = ""
        if img_el:
            # Try srcset first for higher quality, fall back to src
            srcset = img_el.get('srcset', '')
            if srcset:
                # Get the largest image from srcset
                parts = srcset.split(',')
                if parts:
                    last_part = parts[-1].strip().split(' ')[0]
                    image_url = last_part
            if not image_url:
                image_url = img_el.get('src', '')

        # Find date - look for text that matches date pattern
        date_str = ""
        date_divs = item_div.find_all('div', class_='text-size-small')
        for div in date_divs:
            text = div.get_text(strip=True)
            # Match patterns like "October 14, 2025"
            if re.match(r'^[A-Z][a-z]+ \d{1,2}, \d{4}$', text):
                date_str = text
                break

        # Find description
        desc_el = item_div.find('div', class_='text-size-regular')
        description = clean_text(desc_el.get_text()) if desc_el else ""

        # Find category
        category = ""
        cat_link = item_div.find('a', href=re.compile(r'^/category/'))
        if cat_link:
            cat_div = cat_link.find('div', class_='text-size-small')
            if cat_div:
                category = clean_text(cat_div.get_text())

        guid = make_guid(title, full_link)

        items.append({
            "title": title,
            "link": full_link,
            "description": description,
            "image": image_url,
            "guid": guid,
            "pub_date": parse_date(date_str),
            "category": category,
        })

    return items

def build_rss(items):
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Shambhala Music Festival Blog"
    ET.SubElement(channel, "link").text = URL
    ET.SubElement(channel, "description").text = "The latest Shambhala Music Festival news for the Farmily"
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
            ET.SubElement(item, "pubDate").text = it["pub_date"]

        if it.get("image"):
            mc = ET.SubElement(item, "{http://search.yahoo.com/mrss/}content")
            mc.set("url", it["image"])
            mc.set("type", "image/webp")
            ET.SubElement(item, "enclosure", url=it["image"], type="image/webp", length="0")

    tree = ET.ElementTree(rss)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {len(items)} items to {OUTPUT_FILE}")

if __name__ == "__main__":
    posts = scrape_blog()
    if not posts:
        print("No blog posts found — page structure might have changed.")
    build_rss(posts)
