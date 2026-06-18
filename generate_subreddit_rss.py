#!/usr/bin/env python3
import sys
import re
import json
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from html import unescape
from anthropic import Anthropic

# --- CONFIG ---
FETCH_LIMIT  = 25
BATCH_SIZE   = 25
HEADERS      = {"User-Agent": "python:rss-digest:v1.0 (by /u/frownigami)"}
MEDIA_NS     = "http://search.yahoo.com/mrss/"

ET.register_namespace("media", MEDIA_NS)


# --- FETCH POSTS ---
def clean_text(html_text):
    if not html_text:
        return ""
    text = unescape(html_text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_posts(subreddit):
    url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={FETCH_LIMIT}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    articles = []
    for entry in root.findall("atom:entry", ns):
        title   = clean_text(entry.findtext("atom:title", "", ns))
        link_el = entry.find("atom:link", ns)
        link    = link_el.attrib.get("href", "") if link_el is not None else ""
        content = entry.find("atom:content", ns)
        desc    = clean_text(content.text if content is not None else "")[:300]

        # thumbnail
        thumb_el  = entry.find("{http://search.yahoo.com/mrss/}thumbnail")
        image     = None
        if thumb_el is not None:
            image = thumb_el.attrib.get("url")
        elif content is not None and content.text and 'img src="' in content.text:
            match = re.search(r'<img src="([^"]+)"', content.text)
            if match:
                image = match.group(1)

        if title:
            articles.append({"title": title, "link": link, "desc": desc, "image": image})

    print(f"  Fetched {len(articles)} posts from r/{subreddit}")
    return articles


# --- CLAUDE FILTER ---
def filter_posts(articles, subreddit, filter_intent):
    client  = Anthropic()
    kept    = []

    for i in range(0, len(articles), BATCH_SIZE):
        batch    = articles[i:i + BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. {a['title']}" + (f" — {a['desc']}" if a["desc"] else "")
            for j, a in enumerate(batch)
        )

        prompt = f"""You are filtering a Reddit feed for r/{subreddit}.

Filter criteria:
{filter_intent}

Evaluate each post below. Return ONLY a JSON array with one object per post:
[{{"id": 1, "decision": "INCLUDE", "reason": "one sentence reason"}}, ...]

Posts:
{numbered}"""

        try:
            response = Anthropic().messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
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
            print(f"  Batch failed: {e}")

    return kept


# --- BUILD RSS ---
def build_rss(posts, subreddit, output_file):
    rss     = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text       = f"r/{subreddit} Digest"
    ET.SubElement(channel, "link").text        = f"https://reddit.com/r/{subreddit}"
    ET.SubElement(channel, "description").text = f"Filtered posts from r/{subreddit}"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for a in posts:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = a["title"]
        ET.SubElement(item, "link").text        = a["link"]
        ET.SubElement(item, "description").text = (
            f"<p>{a['desc']}</p><p><em>{a.get('reason', '')}</em></p>"
            f'<p><a href="{a["link"]}">View on Reddit</a></p>'
        )
        guid      = ET.SubElement(item, "guid")
        guid.text = hashlib.sha1(a["link"].encode()).hexdigest()
        guid.set("isPermaLink", "false")

        if a.get("image"):
            image_url = a["image"].replace("&amp;", "&")
            mc = ET.SubElement(item, f"{{{MEDIA_NS}}}content")
            mc.set("url", image_url)
            mc.set("medium", "image")

    ET.ElementTree(rss).write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"  Wrote {len(posts)} posts to {output_file}")


# --- MAIN ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_subreddit_rss.py <subreddit> [filter_intent]")
        sys.exit(1)

    subreddit     = sys.argv[1]
    filter_intent = sys.argv[2] if len(sys.argv) > 2 else "Include posts that are interesting or relevant to the community."
    output_file   = f"output/{subreddit}.xml"

    print(f"Processing r/{subreddit}...")
    posts  = fetch_posts(subreddit)
    kept   = filter_posts(posts, subreddit, filter_intent)
    print(f"  Kept {len(kept)} of {len(posts)} posts")
    build_rss(kept, subreddit, output_file)
