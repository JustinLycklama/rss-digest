#!/usr/bin/env python3
"""
songkick_calendar.py — Sync Songkick tracked events to Google Calendar

Fetches the Songkick iCal feed, finds events not already in the target
calendar, and creates them. Runs as part of the daily CI pipeline.

Required env vars:
  GCAL_CLIENT_ID
  GCAL_CLIENT_SECRET
  GCAL_REFRESH_TOKEN
"""

import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- CONFIG ---
SONGKICK_ICAL_URL = "http://www.songkick.com/users/justin-lycklama/calendars.ics"
TARGET_CALENDAR   = "Random City Events"
LOOK_AHEAD_DAYS   = 180  # only create events within this window


# --- GOOGLE CALENDAR CLIENT ---
def get_calendar_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GCAL_REFRESH_TOKEN"],
        client_id=os.environ["GCAL_CLIENT_ID"],
        client_secret=os.environ["GCAL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("calendar", "v3", credentials=creds)


def find_calendar_id(service, name):
    calendars = service.calendarList().list().execute().get("items", [])
    for cal in calendars:
        if cal["summary"] == name:
            return cal["id"]
    raise ValueError(f"Calendar '{name}' not found. Available: {[c['summary'] for c in calendars]}")


# --- ICAL PARSER ---
def parse_ical(content):
    """Parse VEVENT blocks from iCal content, return list of event dicts."""
    events = []
    for block in re.split(r"BEGIN:VEVENT", content):
        if "END:VEVENT" not in block:
            continue

        def field(name):
            match = re.search(rf"^{name}[;:][^\n]*?:(.*?)(?=\r?\n[A-Z])", block, re.MULTILINE | re.DOTALL)
            if not match:
                match = re.search(rf"^{name}:(.*)", block, re.MULTILINE)
            return match.group(1).strip().replace("\r", "") if match else ""

        uid       = field("UID")
        summary   = field("SUMMARY")
        location  = field("LOCATION")
        url       = field("URL")
        dtstart   = field("DTSTART")
        dtend     = field("DTEND")
        desc      = field("DESCRIPTION")

        if not uid or not summary or not dtstart:
            continue

        events.append({
            "uid":      uid,
            "summary":  summary,
            "location": location,
            "url":      url,
            "dtstart":  dtstart,
            "dtend":    dtend,
            "desc":     desc,
        })

    return events


def parse_dt(dt_str):
    """Parse iCal datetime string to datetime object."""
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" in dt_str:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.strptime(dt_str, "%Y%m%d").replace(tzinfo=timezone.utc)


def to_gcal_dt(dt_str):
    """Convert iCal datetime string to Google Calendar dateTime dict."""
    dt = parse_dt(dt_str)
    if "T" not in dt_str and not dt_str.endswith("Z"):
        return {"date": dt.strftime("%Y-%m-%d")}
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"}


# --- SYNC ---
def get_existing_uids(service, calendar_id):
    """Fetch existing event UIDs from the target calendar via extended properties."""
    existing = set()
    page_token = None
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=7)).isoformat()

    while True:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            privateExtendedProperty="songkick=true",
            pageToken=page_token,
            maxResults=250,
        ).execute()

        for event in result.get("items", []):
            uid = event.get("extendedProperties", {}).get("private", {}).get("songkickUid")
            if uid:
                existing.add(uid)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return existing


def create_event(service, calendar_id, event):
    dt = parse_dt(event["dtstart"])
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=LOOK_AHEAD_DAYS)

    if dt < now or dt > cutoff:
        return False

    description = event["desc"]
    if event["url"]:
        description = f"{event['url']}\n\n{description}" if description else event["url"]

    body = {
        "summary":  event["summary"],
        "location": event["location"],
        "description": description,
        "start":    to_gcal_dt(event["dtstart"]),
        "end":      to_gcal_dt(event["dtend"]) if event["dtend"] else to_gcal_dt(event["dtstart"]),
        "extendedProperties": {
            "private": {
                "songkick":    "true",
                "songkickUid": event["uid"],
            }
        },
    }

    service.events().insert(calendarId=calendar_id, body=body).execute()
    return True


# --- MAIN ---
if __name__ == "__main__":
    print("Fetching Songkick iCal feed...")
    with urllib.request.urlopen(SONGKICK_ICAL_URL) as r:
        content = r.read().decode("utf-8")

    events = parse_ical(content)
    print(f"  Found {len(events)} events in feed")

    if not events:
        print("  Feed is empty, nothing to sync")
        raise SystemExit(0)

    print("Connecting to Google Calendar...")
    service     = get_calendar_service()
    calendar_id = find_calendar_id(service, TARGET_CALENDAR)
    print(f"  Target calendar: {TARGET_CALENDAR} ({calendar_id})")

    existing_uids = get_existing_uids(service, calendar_id)
    print(f"  Existing Songkick events: {len(existing_uids)}")

    created = 0
    skipped = 0
    for event in events:
        if event["uid"] in existing_uids:
            skipped += 1
            continue
        if create_event(service, calendar_id, event):
            print(f"  + {event['summary']}")
            created += 1
        else:
            skipped += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}")
