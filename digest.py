import requests
import xml.etree.ElementTree as ET
import subprocess
from datetime import datetime
from html import unescape
import re

# --- CONFIG ---
SUBREDDIT = "TorontoRaves"
POST_LIMIT = 3
COMMENT_LIMIT = 1
OUTPUT_FILE = "feed.xml"
HEADERS = {"User-Agent": "RSS Digest 1.0 by /u/yourusername"}

# --- CLEAN HTML TEXT ---
def clean_text(html_text):
    if not html_text:
        return ""
    # unescape HTML entities
    text = unescape(html_text)
    # remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    return text

# --- FETCH POSTS ---
def fetch_posts(subreddit, limit):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?sort=top&t=day&limit={limit}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    data = r.json()["data"]["children"]
    return data

# --- FETCH COMMENTS ---
def fetch_comments(post_id, limit):
    url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    comments = r.json()[1]["data"]["children"]
    return [c["data"]["body"] for c in comments if c["kind"] == "t1"][:limit]

# --- BUILD RSS ---
def build_rss(posts):
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"Reddit Digest: r/{SUBREDDIT}"
    ET.SubElement(channel, "link").text = f"https://reddit.com/r/{SUBREDDIT}"
    ET.SubElement(channel, "description").text = f"Daily digest with top {COMMENT_LIMIT} comments"
    ET.SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    for p in posts:
        post_id = p["data"]["id"]
        title = p["data"]["title"]
        link = "https://reddit.com" + p["data"]["permalink"]
        comments = fetch_comments(post_id, COMMENT_LIMIT)

        # clean text
        desc = clean_text(p["data"].get("selftext", ""))
        if comments:
            desc += "\n\n---\nTop comment:\n" + clean_text(comments[0])

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "description").text = desc

        # --- STABLE GUID ---
        guid = ET.SubElement(item, "guid")
        guid.text = post_id
        guid.set("isPermaLink", "true")

        # --- IMAGE LOGIC ---
        preview = p["data"].get("preview")
        if preview and "images" in preview and len(preview["images"]) > 0:
            img_url = preview["images"][0]["source"]["url"]

            # media:content for RSS preview support
            media_content = ET.SubElement(item, '{http://search.yahoo.com/mrss/}content')
            media_content.set("url", img_url)
            media_content.set("type", "image/jpeg")

            # prepend image in description for backup
            item.find("description").text = f'<img src="{img_url}" /><br>{desc}'

    return ET.ElementTree(rss)

# --- MAIN ---
if __name__ == "__main__":
    posts = fetch_posts(SUBREDDIT, POST_LIMIT)
    rss_tree = build_rss(posts)
    rss_tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    # optional: push to GitHub
    subprocess.run(["git", "checkout", "gh-pages"])
    subprocess.run(["git", "rebase", "main"])
    subprocess.run(["git", "add", OUTPUT_FILE])
    subprocess.run(["git", "commit", "-m", "Update daily feed", "--amend"])
    subprocess.run(["git", "push", "-f"])
    subprocess.run(["git", "checkout", "main"])

