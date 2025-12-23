#!/usr/bin/env python3
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
import re

# --- CONFIG ---
SUBREDDIT = "TorontoRaves"
POST_LIMIT = 10
COMMENT_LIMIT = 10
OUTPUT_FILE = "output/feed.xml"

HEADERS = {"User-Agent": "RSS Digest 1.0 by /u/frownigami"}
RSS_URL = f"https://www.reddit.com/r/{SUBREDDIT}/.rss"
COMMENTS_BASE = "https://old.reddit.com"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


# --- CLEAN HTML TEXT ---
def clean_text(html_text):
    if not html_text:
        return ""
    text = unescape(html_text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


# --- FETCH POSTS (RSS → limited locally) ---
def fetch_posts(limit):
    r = requests.get(RSS_URL, headers=HEADERS)
    r.raise_for_status()

    root = ET.fromstring(r.content)
    entries = root.findall("atom:entry", ATOM_NS)

    posts = []
    for entry in entries[:limit]:
        link = entry.find("atom:link", ATOM_NS).attrib["href"]
        post_id = link.rstrip("/").split("/")[-1]

        posts.append({
            "id": post_id,
            "title": entry.find("atom:title", ATOM_NS).text,
            "link": link,
            "content": entry.find("atom:content", ATOM_NS).text or "",
        })

    return posts


# --- FETCH COMMENTS (best-effort) ---
def fetch_comments(post_id, limit):
    url = f"{COMMENTS_BASE}/comments/{post_id}.json?raw_json=1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        children = r.json()[1]["data"]["children"]
        return [
            c["data"]["body"]
            for c in children
            if c.get("kind") == "t1"
        ][:limit]
    except Exception:
        return []


# --- BUILD RSS ---
def build_rss(posts):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = f"Reddit Digest: r/{SUBREDDIT}"
    ET.SubElement(channel, "link").text = f"https://reddit.com/r/{SUBREDDIT}"
    ET.SubElement(channel, "description").text = (
        f"Top {POST_LIMIT} posts, up to {COMMENT_LIMIT} comments each"
    )
    ET.SubElement(channel, "lastBuildDate").text = (
        datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    )

    for p in posts:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = p["title"]
        ET.SubElement(item, "link").text = p["link"]

        desc = clean_text(p["content"])

        comments = fetch_comments(p["id"], COMMENT_LIMIT)
        if comments:
            desc += "\n\n---\nTop comments:\n"
            desc += "\n\n".join(f"- {clean_text(c)}" for c in comments)

        ET.SubElement(item, "description").text = desc

        guid = ET.SubElement(item, "guid", isPermaLink="true")
        guid.text = p["link"]

    return ET.ElementTree(rss)


# --- MAIN ---
if __name__ == "__main__":
    posts = fetch_posts(POST_LIMIT)
    print(f"Fetched {len(posts)} posts")

    rss_tree = build_rss(posts)
    rss_tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)