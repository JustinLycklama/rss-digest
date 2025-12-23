#!/usr/bin/env python3
import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
import re

# --- CONFIG ---
SUBREDDIT = ""
POST_LIMIT = 15
OUTPUT_FILE = ""

HEADERS = {"User-Agent": "RSS Digest 1.0 by /u/frownigami"}

# --- CLEAN HTML TEXT ---
def clean_text(html_text):
    if not html_text:
        return ""
    text = unescape(html_text)
    text = re.sub(r'<[^>]+>', '', text)
    return text

# --- FETCH POSTS ---
def fetch_posts(subreddit, limit):
    url = f"https://www.reddit.com/r/{subreddit}/.rss"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('atom:entry', ATOM_NS)
    return entries[:limit]

# --- BUILD RSS ---
def build_rss(posts):
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"Reddit Digest: r/{SUBREDDIT}"
    ET.SubElement(channel, "link").text = f"https://reddit.com/r/{SUBREDDIT}"
    ET.SubElement(channel, "description").text = f"Daily digest linking to top posts"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}
    MEDIA_NS = 'http://search.yahoo.com/mrss/'

    for entry in posts:
        title = entry.find('atom:title', ATOM_NS).text
        link = entry.find('atom:link', ATOM_NS).attrib['href']
        content = entry.find('atom:content', ATOM_NS)
        desc_text = clean_text(content.text) if content is not None else ""

        # Include post flair if present
        flair_el = entry.find("{http://www.w3.org/2005/Atom}category")
        flair_text = flair_el.attrib.get('term') if flair_el is not None else ""
        flair_prefix = f"[{flair_text}] " if flair_text else ""

        # Build description with spacing and clickable link
        desc_lines = [
            f"<p>{flair_prefix}{desc_text}</p>",
            f'<p><a href="{link}">View discussion on Reddit</a></p>'
        ]
        desc = "\n".join(desc_lines)

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "description").text = desc

        guid = ET.SubElement(item, "guid")
        guid.text = link
        guid.set("isPermaLink", "true")

        # --- IMAGE / THUMBNAIL ---
        thumb_el = entry.find('{http://search.yahoo.com/mrss/}thumbnail')
        thumb_url = None
        if thumb_el is not None:
            thumb_url = thumb_el.attrib.get('url')
        else:
            # fallback: check for content preview in <content type="html">
            if content is not None and 'img src="' in content.text:
                match = re.search(r'<img src="([^"]+)"', content.text)
                if match:
                    thumb_url = match.group(1)
        if thumb_url:
            # fix &amp; in URLs
            thumb_url = thumb_url.replace("&amp;", "&")

            media_content = ET.SubElement(item, f'{{{MEDIA_NS}}}content')
            media_content.set("url", thumb_url)
            media_content.set("type", "image/jpeg")
            # prepend image in description for fallback
            item.find("description").text = f'<p><img src="{thumb_url}" /></p>' + desc

    return ET.ElementTree(rss)

# --- MAIN ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_reddit_rss.py <subreddit>")
        sys.exit(1)

    SUBREDDIT = sys.argv[1]
    OUTPUT_FILE = f"output/{SUBREDDIT}.xml"

    posts = fetch_posts(SUBREDDIT, POST_LIMIT)
    print(f"Fetched {len(posts)} posts")
    rss_tree = build_rss(posts)
    rss_tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Wrote feed to {OUTPUT_FILE}")