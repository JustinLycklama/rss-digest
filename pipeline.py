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
from feeds_config import FEEDS

MEDIA_NS       = "http://search.yahoo.com/mrss/"
OUTPUT_DIR     = Path("output")
BATCH_SIZE     = 40
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
FILTER_PAGE_ID = "33ba1339f88a81799204f8b0d4a1ca71"

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

def load_notion_filter():
    if not NOTION_TOKEN:
        print("  No NOTION_TOKEN, using default filter context")
        return DEFAULT_FILTER_CONTEXT
    try:
        url = f"https://api.notion.com/v1/blocks/{FILTER_PAGE_ID}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        blocks = r.json().get("results", [])
        lines = []
        for block in blocks:
            btype = block.get("type")
            rich  = block.get(btype, {}).get("rich_text", [])
            text  = "".join(t.get("plain_text", "") for t in rich)
            if text.strip():
                lines.append(text.strip())
        if lines:
            print("  Loaded filter context from Notion")
            return "\n".join(lines)
    except Exception as e:
        print(f"  Could not fetch Notion filter: {e} — using defaults")
    return DEFAULT_FILTER_CONTEXT


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
def filter_articles(articles, filter_context, client):
    kept = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch    = articles[i:i + BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. [{a['source']}] {a['title']}" + (f" — {a['desc']}" if a["desc"] else "")
            for j, a in enumerate(batch)
        )
        prompt = f"""You are filtering a feed for a personal digest.

{filter_context}

Evaluate each article below. Return ONLY a JSON array with one object per article:
[{{"id": 1, "decision": "INCLUDE", "reason": "one sentence reason"}}, ...]

Articles:
{numbered}"""

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
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
            print(f"  Batch {i // BATCH_SIZE + 1} failed: {e}")

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
        ET.SubElement(item, "title").text = a["title"]
        ET.SubElement(item, "link").text  = a["link"]

        reason = a.get("reason", "")
        source = a.get("source", "")
        desc   = a.get("desc", "")
        if reason:
            ET.SubElement(item, "description").text = f"<p>{desc}</p><p><em>{source} — {reason}</em></p>"
        else:
            ET.SubElement(item, "description").text = f"<p>{desc}</p>"

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
    OUTPUT_DIR.mkdir(exist_ok=True)
    client = Anthropic() if any(f.filter_prompt for f in FEEDS) else None

    for feed in FEEDS:
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
            prompt = load_notion_filter() if feed.filter_prompt == "NOTION" else feed.filter_prompt
            kept   = filter_articles(new_articles, prompt, client)
            print(f"  Kept: {len(kept)}")
        else:
            kept = new_articles

        archive = merge_into_archive(archive, kept, feed.archive_days)
        save_archive(feed.name, archive)

        build_rss(feed, archive)

    print("\nDone.")
