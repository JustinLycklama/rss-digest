#!/usr/bin/env python3
"""
daviestudios_shows_rss.py
Scrape https://daviestudios.com/shows and produce daviestudios_shows.xml
Requires: requests, beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
import hashlib
import re

URL = "https://daviestudios.com/shows"
OUTPUT_FILE = "output/daviestudios.xml"

HEADERS = {"User-Agent": "DavieShowsRSS/1.0 (+https://yourdomain.example)"}
MAX_DESC_CHARS = 2000  # trim long descriptions

def clean_text(s: str) -> str:
    if not s:
        return ""
    text = unescape(s)
    # compress whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def make_guid(title: str, link: str) -> str:
    h = hashlib.sha1()
    h.update((title + '||' + (link or "")).encode("utf-8"))
    return h.hexdigest()

def scrape_shows():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # find headings that look like show titles (h3 is used on that page)
    headings = soup.find_all(['h2', 'h3', 'h4'])
    items = []

    for idx, h in enumerate(headings):
        title = clean_text(h.get_text(separator=" ", strip=True))
        # skip headings that look like section headers (e.g. "Shows", "Future live shows")
        if not title or len(title) < 3:
            continue
        # collect nodes until next heading of same or higher weight
        block_nodes = []
        for sib in h.next_siblings:
            if isinstance(sib, Tag) and sib.name in ['h2', 'h3', 'h4']:
                break
            block_nodes.append(sib)

        # extract image, link, description text from the block
        image_url = None
        first_link = None
        desc_parts = []

        for node in block_nodes:
            if isinstance(node, Tag):
                # find first image inside this block
                if image_url is None:
                    img = node.find('img')
                    if img and img.get('src'):
                        image_url = img['src']
                # find first link (prefer eventbrite / absolute links)
                if first_link is None:
                    a = node.find('a', href=True)
                    if a:
                        href = a['href']
                        # prefer eventbrite or absolute links
                        if 'eventbrite' in href or href.startswith('http'):
                            first_link = href
                        else:
                            # fallback to relative
                            first_link = requests.compat.urljoin(URL, href)
                # collect textual content
                text = node.get_text(" ", strip=True)
                if text:
                    desc_parts.append(text)
            elif isinstance(node, NavigableString):
                t = str(node).strip()
                if t:
                    desc_parts.append(t)

        description = clean_text(" ".join(desc_parts))
        if len(description) > MAX_DESC_CHARS:
            description = description[:MAX_DESC_CHARS].rsplit(" ", 1)[0] + "…"

        # If we couldn't find a link in the block, try to fallback to any link near the title
        if not first_link:
            a_near = h.find_next('a', href=True)
            if a_near:
                first_link = a_near['href']
                if not first_link.startswith('http'):
                    first_link = requests.compat.urljoin(URL, first_link)

        # If the title contains leading markdown-like ### clean it
        title = title.lstrip('#').strip()

        # Build item structure
        guid = make_guid(title, first_link or "")
        item = {
            "title": title,
            "link": first_link or URL,
            "description": description,
            "image": image_url,
            "guid": guid
        }
        # Only include if title looks like an event (heuristic: contains words, not section headings)
        # Accept titles longer than 3 chars and not equal to "More events" etc.
        if re.search(r'[A-Za-z0-9]', title) and not re.match(r'(?i)more events|future live shows|shows', title):
            items.append(item)

    return items

def build_rss(items):
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Davie Studios — Shows"
    ET.SubElement(channel, "link").text = URL
    ET.SubElement(channel, "description").text = "Upcoming shows at Davie Studios"
    ET.SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it["title"]
        ET.SubElement(item, "link").text = it["link"]
        desc_el = ET.SubElement(item, "description")
        desc_el.text = it["description"] or ""

        guid_el = ET.SubElement(item, "guid")
        guid_el.text = it["guid"]
        guid_el.set("isPermaLink", "false")

        # add media:content if image available
        if it.get("image"):
            mc = ET.SubElement(item, "{http://search.yahoo.com/mrss/}content")
            mc.set("url", it["image"])
            mc.set("type", "image/jpeg")
            # also add enclosure for compatibility
            ET.SubElement(item, "enclosure", url=it["image"], type="image/jpeg")

    # write xml pretty-ish
    tree = ET.ElementTree(rss)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {len(items)} items to {OUTPUT_FILE}")

if __name__ == "__main__":
    shows = scrape_shows()
    if not shows:
        print("No shows found — page structure might have changed.")
    build_rss(shows)

