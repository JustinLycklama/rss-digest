#!/usr/bin/env python3
"""
pipeline.py — Unified RSS feed pipeline

For each feed defined in feeds_config.py:
  1. Fetch all sources
  2. Skip articles already in the rolling archive
  3. Run Claude filter (if configured)
  4. Merge new articles into archive, prune old ones
  5. Write output/<name>.xml from the archive

Feeds with filter_prompt=None skip Claude and write source output directly.
"""

import os
import re
import json
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
from pathlib import Path

from anthropic import Anthropic
import argparse
from feeds_config import FEEDS
from sources.rss import _scraper

MEDIA_NS              = "http://search.yahoo.com/mrss/"
OUTPUT_DIR            = Path("output")
BATCH_SIZE            = 20
NOTION_TOKEN          = os.environ.get("NOTION_TOKEN")
FILTER_PAGE_ID        = "33ba1339f88a81799204f8b0d4a1ca71"
MEDIA_RECS_FILTER_ID  = "398a1339f88a819ca5d4c6491a4d7230"
MEDIA_COLLECTION_ID   = "1482e7dbf30d47409a002ab3413d8177"
GOODREADS_RSS         = "https://www.goodreads.com/review/list_rss/197955244?shelf=read"

ET.register_namespace("media", MEDIA_NS)


# --- NOTION ---
DEFAULT_FILTER_CONTEXT = """
The user wants a daily digest of significant world news. Apply these rules:

INCLUDE:
- Wars: escalation, de-escalation, major battles, peace deals
- Regime changes: elections with major outcomes, coups, leaders captured/killed
- Major economic policy: tariffs with significant global impact, market crashes, major sanctions
- Space launches and milestones
- Major tech product launches or significant company events (not funding rounds or layoffs)
- Natural disasters at large scale
- Major scientific breakthroughs

EXCLUDE:
- Day-to-day political back-and-forth
- Crime (unless a major world event)
- Celebrity, entertainment, sports
- Incremental follow-up stories unless something major changed
- Local news

SIGNIFICANCE TEST: Would this story still matter in a week? If no, exclude it.
"""

def _fetch_notion_page_text(page_id):
    """Return plain text content of a Notion page, or None on failure."""
    if not NOTION_TOKEN:
        return None
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        lines = []
        for block in r.json().get("results", []):
            btype = block.get("type")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text.strip():
                lines.append(text.strip())
        return "\n".join(lines) if lines else None
    except Exception as e:
        print(f"  Could not fetch Notion page {page_id}: {e}")
        return None

def load_notion_filter():
    if not NOTION_TOKEN:
        print("  No NOTION_TOKEN, using default filter context")
        return DEFAULT_FILTER_CONTEXT
    text = _fetch_notion_page_text(FILTER_PAGE_ID)
    if text:
        print("  Loaded filter context from Notion")
        return text
    print("  Could not fetch Notion filter — using defaults")
    return DEFAULT_FILTER_CONTEXT


# --- TASTE PROFILE ---
def load_taste_profile():
    parts = []

    # Goodreads — books rated 4 or 5 stars
    try:
        r = _scraper.get(GOODREADS_RSS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        books = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            rating_text = (item.findtext("user_rating") or "").strip()
            rating = int(rating_text) if rating_text.isdigit() else 0
            if rating >= 4 and title:
                label = "loved it" if rating == 5 else "liked it"
                books.append(f"- {title} ({label})")
        if books:
            parts.append("Books the user has rated highly:\n" + "\n".join(books[:25]))
        print(f"  Goodreads: {len(books)} highly-rated books")
    except Exception as e:
        print(f"  Goodreads: failed ({e})")

    # Notion Media Collection — games, film, TV
    if NOTION_TOKEN:
        try:
            url = f"https://api.notion.com/v1/databases/{MEDIA_COLLECTION_ID}/query"
            headers = {
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }
            r = requests.post(url, headers=headers, json={}, timeout=10)
            r.raise_for_status()
            entries = []
            for page in r.json().get("results", []):
                props = page.get("properties", {})
                name  = "".join(t.get("plain_text", "") for t in props.get("Name", {}).get("title", []))
                mtype = (props.get("Type", {}).get("select") or {}).get("name", "")
                notes = "".join(t.get("plain_text", "") for t in props.get("Notes", {}).get("rich_text", []))
                if name:
                    entry = f"- {name}" + (f" ({mtype})" if mtype else "") + (f": {notes}" if notes else "")
                    entries.append(entry)
            if entries:
                parts.append("Other media the user has loved (games, film, TV):\n" + "\n".join(entries))
            print(f"  Notion collection: {len(entries)} entries")
        except Exception as e:
            print(f"  Notion media collection: failed ({e})")

    if not parts:
        print("  No taste profile available — skipping filter")
        return None

    profile = "\n\n".join(parts)

    rules = _fetch_notion_page_text(MEDIA_RECS_FILTER_ID)
    if rules:
        print("  Loaded media recs filter rules from Notion")
    else:
        rules = "Include recommendations for specific titles. Exclude news, trailers, announcements, and industry coverage."

    return f"""You are filtering media recommendation articles for a specific reader.

Here is their taste profile:
{profile}

Here are the filter rules:
{rules}"""


# --- ARCHIVE ---
def archive_path(feed_name):
    return OUTPUT_DIR / f"{feed_name}_archive.json"

def load_archive(feed_name):
    path = archive_path(feed_name)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  Could not load archive: {e} — starting fresh")
        return []

def save_archive(feed_name, archive):
    with open(archive_path(feed_name), "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

def merge_into_archive(archive, new_articles, archive_days):
    existing_guids = {a["guid"] for a in archive}
    now = datetime.now(UTC)

    for a in new_articles:
        if a["guid"] not in existing_guids:
            a["added_at"] = now.isoformat()
            archive.append(a)
            existing_guids.add(a["guid"])

    cutoff = now.timestamp() - archive_days * 86400
    archive = [
        a for a in archive
        if datetime.fromisoformat(a["added_at"]).timestamp() > cutoff
    ]
    archive.sort(key=lambda a: a["added_at"], reverse=True)
    return archive


# --- DATE FILTER ---
def filter_by_pub_date(articles, archive_days):
    """Drop articles with a pub_date older than archive_days. Articles with no date pass through."""
    cutoff = datetime.now(UTC).timestamp() - archive_days * 86400
    out = []
    for a in articles:
        pd = a.get("pub_date", "")
        if not pd:
            out.append(a)
            continue
        try:
            dt = parsedate_to_datetime(pd)
            if dt.timestamp() >= cutoff:
                out.append(a)
        except Exception:
            out.append(a)
    return out


# --- DEDUP ---
def dedup_by_title(articles):
    """Remove near-duplicates based on first 6 words of title (catches cross-source repeats)."""
    seen = {}
    out  = []
    for a in articles:
        key = " ".join(a["title"].lower().split()[:6])
        if key not in seen:
            seen[key] = True
            out.append(a)
    return out


# --- CLAUDE FILTER ---
def filter_articles(articles, filter_context, client, classify_type=False):
    kept = []
    type_schema = ', "type": "Game|Film|Book|TV|Other"' if classify_type else ""
    for i in range(0, len(articles), BATCH_SIZE):
        batch    = articles[i:i + BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. [{a['source']}] {a['title']}" + (f" — {a['desc']}" if a["desc"] else "")
            for j, a in enumerate(batch)
        )
        prompt = f"""You are filtering a feed for a personal digest.

{filter_context}

Evaluate each article below. Return ONLY a JSON array with one object per article:
[{{"id": 1, "decision": "INCLUDE", "reason": "one sentence reason"{type_schema}}}, ...]

Articles:
{numbered}"""

        decisions = None
        for attempt in range(2):
            try:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text.strip()
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                if not match:
                    raise ValueError("No JSON array found in response")
                decisions = json.loads(match.group(0))
                break
            except Exception as e:
                print(f"  Batch {i // BATCH_SIZE + 1} attempt {attempt + 1} failed: {e}")

        if decisions:
            for d in decisions:
                idx = d["id"] - 1
                if 0 <= idx < len(batch) and d["decision"] == "INCLUDE":
                    article = batch[idx].copy()
                    article["reason"] = d.get("reason", "")
                    if classify_type:
                        article["media_type"] = d.get("type", "")
                    kept.append(article)
                    print(f"  + {batch[idx]['title'][:70]}")

    return kept


# --- RSS OUTPUT ---
def build_rss(feed, articles):
    rss     = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text        = feed.title
    ET.SubElement(channel, "link").text         = "https://justinlycklama.github.io/rss-digest/"
    ET.SubElement(channel, "description").text  = feed.description
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

    for a in articles:
        item = ET.SubElement(channel, "item")
        media_type = a.get("media_type", "")
        title = f"{media_type}: {a['title']}" if media_type and media_type != "Other" else a["title"]
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text  = a["link"]

        reason = a.get("reason", "")
        source = a.get("source", "")
        desc   = a.get("desc", "")
        footer = f"{source} — {reason}" if reason else source
        ET.SubElement(item, "description").text = f"<p>{desc}</p><p><em>{footer}</em></p>"

        guid_el      = ET.SubElement(item, "guid")
        guid_el.text = a["guid"]
        guid_el.set("isPermaLink", "false")

        if a.get("pub_date"):
            ET.SubElement(item, "pubDate").text = a["pub_date"]

        if a.get("image"):
            mc = ET.SubElement(item, f"{{{MEDIA_NS}}}content")
            mc.set("url", a["image"])
            mc.set("medium", "image")

    out_path = OUTPUT_DIR / f"{feed.name}.xml"
    ET.ElementTree(rss).write(str(out_path), encoding="utf-8", xml_declaration=True)
    print(f"  Wrote {len(articles)} articles to {out_path}")


# --- MAIN ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--feeds", help="Comma-separated feed names to run (default: all)")
    args = parser.parse_args()
    selected = set(args.feeds.split(",")) if args.feeds else None
    feeds_to_run = [f for f in FEEDS if selected is None or f.name in selected]

    OUTPUT_DIR.mkdir(exist_ok=True)
    client = Anthropic() if any(f.filter_prompt for f in feeds_to_run) else None

    for feed in feeds_to_run:
        print(f"\n=== {feed.name} ===")

        archive        = load_archive(feed.name)
        archive_guids  = {a["guid"] for a in archive}
        print(f"  Archive: {len(archive)} articles")

        articles = []
        for source in feed.sources:
            articles.extend(source.fetch())

        articles     = filter_by_pub_date(articles, feed.archive_days)
        articles     = dedup_by_title(articles)
        new_articles = [a for a in articles if a["guid"] not in archive_guids]
        print(f"  {len(new_articles)} new articles")

        if feed.filter_prompt:
            if feed.filter_prompt == "NOTION":
                prompt = load_notion_filter()
            elif feed.filter_prompt == "TASTE_PROFILE":
                prompt = load_taste_profile()
            else:
                prompt = feed.filter_prompt

            if prompt:
                classify = feed.filter_prompt == "TASTE_PROFILE"
                kept = filter_articles(new_articles, prompt, client, classify_type=classify)
                print(f"  Kept: {len(kept)}")
            else:
                kept = []
        else:
            kept = new_articles

        archive = merge_into_archive(archive, kept, feed.archive_days)
        save_archive(feed.name, archive)

        build_rss(feed, archive)

    print("\nDone.")
