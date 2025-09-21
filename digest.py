import requests
import datetime
import xml.etree.ElementTree as ET

SUBREDDIT = "AskHistorians"
POST_LIMIT = 5  # number of posts per day
COMMENT_LIMIT = 1  # number of comments per post

def fetch_posts(subreddit, limit=5):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?sort=new&t=day&limit={limit}"
    headers = {"User-Agent": "reddit-rss-script/0.1"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()["data"]["children"]

def fetch_comments(post_id, limit=1):
    url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}&sort=top"
    headers = {"User-Agent": "reddit-rss-script/0.1"}
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
        ET.SubElement(item, "description").text = desc

    return ET.ElementTree(rss)

if __name__ == "__main__":
    posts = fetch_posts(SUBREDDIT, POST_LIMIT)
    rss_tree = build_rss(posts)
    rss_tree.write("feed.xml", encoding="utf-8", xml_declaration=True)

