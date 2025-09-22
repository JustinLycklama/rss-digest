import requests
import datetime
import xml.etree.ElementTree as ET
import subprocess
from bs4 import BeautifulSoup

SUBREDDIT = "TorontoRaves"
POST_LIMIT = 5  # number of posts per day
COMMENT_LIMIT = 1  # number of comments per post

def fetch_posts(subreddit, limit=5):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?sort=new&t=day&limit={limit}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/114.0.0.0 Safari/537.36"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()["data"]["children"]

def fetch_comments(post_id, limit=1):
    url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}&sort=top"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/114.0.0.0 Safari/537.36"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    comments = r.json()[1]["data"]["children"]
    return [c["data"]["body"] for c in comments if c["kind"] == "t1"][:limit]

def build_rss(posts):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"Reddit Digest: r/{SUBREDDIT}"
    ET.SubElement(channel, "link").text = f"https://reddit.com/r/{SUBREDDIT}"
    ET.SubElement(channel, "description").text = f"Daily digest with top {COMMENT_LIMIT} comments"

    for p in posts:
        post_id = p["data"]["id"]
        title = p["data"]["title"]
        link = "https://reddit.com" + p["data"]["permalink"]
        comments = fetch_comments(post_id, COMMENT_LIMIT)

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link
        desc = p["data"].get("selftext", "")
        if comments:
            desc += "\n\n---\nTop comment:\n" + comments[0]
            
            # --- IMAGE LOGIC ---
        img_url = None
        preview = p["data"].get("preview")
        if preview and "images" in preview and len(preview["images"]) > 0:
            img_url = preview["images"][0]["source"]["url"]
            ET.SubElement(item, "enclosure", url=img_url, type="image/jpeg")
            desc = f'<img src="{img_url}" /><br>' + desc

        ET.SubElement(item, "description").text = desc

    return ET.ElementTree(rss)

if __name__ == "__main__":
    posts = fetch_posts(SUBREDDIT, POST_LIMIT)
    rss_tree = build_rss(posts)
    rss_tree.write("feed.xml", encoding="utf-8", xml_declaration=True)

# after feed.xml is written
subprocess.run(["git", "add", "feed.xml"])
subprocess.run(["git", "commit", "-m", "Update daily feed"])
subprocess.run(["git", "push"])
