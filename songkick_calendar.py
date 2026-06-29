#!/usr/bin/env python3
"""
songkick_calendar.py — Sync Songkick tracked events to Google Calendar

Fetches the Songkick iCal feed for tracked artists, routes each event to a
city-specific Google Calendar, and skips events already created.

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
SONGKICK_ICAL_URL = "http://www.songkick.com/users/justin-lycklama/calendars.ics?filter=tracked_artist"
LOOK_AHEAD_DAYS   = 180

# Maps city keywords (lowercase, checked against event location) to Google Calendar name
CITY_CALENDARS = {
    "toronto":     "Potential Shows - Toronto",
    "new york":    "Potential Shows - New York",
    "brooklyn":    "Potential Shows - New York",
    "montreal":    "Potential Shows - Montreal",
    "seattle":     "Potential Shows - Seattle",
    "minneapolis": "Potential Shows - Minneapolis",
}


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
    events = []
    for block in re.split(r"BEGIN:VEVENT", content):
        if "END:VEVENT" not in block:
            continue

        def field(name):
            match = re.search(rf"^{name}[;:][^\n]*?:(.*?)(?=\r?\n[A-Z])", block, re.MULTILINE | re.DOTALL)
            if not match:
                match = re.search(rf"^{name}:(.*)", block, re.MULTILINE)
            return match.group(1).strip().replace("\r", "") if match else ""

        uid      = field("UID")
        summary  = field("SUMMARY")
        location = field("LOCATION")
        url      = field("URL")
        dtstart  = field("DTSTART")
        dtend    = field("DTEND")
        desc     = field("DESCRIPTION")

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


def match_city_calendar(location):
    """Return the Google Calendar name for this event's location, or None if no match."""
    loc_lower = location.lower()
    for keyword, calendar_name in CITY_CALENDARS.items():
        if keyword in loc_lower:
            return calendar_name
    return None


def parse_dt(dt_str):
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if "T" in dt_str:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.strptime(dt_str, "%Y%m%d").replace(tzinfo=timezone.utc)


def to_gcal_dt(dt_str):
    dt = parse_dt(dt_str)
    if "T" not in dt_str and not dt_str.endswith("Z"):
        return {"date": dt.strftime("%Y-%m-%d")}
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": "UTC"}


# --- SYNC ---
def get_existing_uids(service, calendar_id):
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
    if dt < now or dt > now + timedelta(days=LOOK_AHEAD_DAYS):
        return False

    description = event["desc"]
    if event["url"]:
        description = f"{event['url']}\n\n{description}" if description else event["url"]

    body = {
        "summary":     event["summary"],
        "location":    event["location"],
        "description": description,
        "start":       to_gcal_dt(event["dtstart"]),
        "end":         to_gcal_dt(event["dtend"]) if event["dtend"] else to_gcal_dt(event["dtstart"]),
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
    service = get_calendar_service()

    # Load all city calendar IDs and their existing UIDs
    calendar_ids = {}
    existing_uids = {}
    for calendar_name in set(CITY_CALENDARS.values()):
        cal_id = find_calendar_id(service, calendar_name)
        calendar_ids[calendar_name] = cal_id
        existing_uids[calendar_name] = get_existing_uids(service, cal_id)
        print(f"  {calendar_name}: {len(existing_uids[calendar_name])} existing events")

    created = 0
    skipped = 0
    for event in events:
        calendar_name = match_city_calendar(event["location"])
        if not calendar_name:
            print(f"  - Skipping (no city match): {event['summary']} @ {event['location']}")
            skipped += 1
            continue

        if event["uid"] in existing_uids[calendar_name]:
            skipped += 1
            continue

        cal_id = calendar_ids[calendar_name]
        if create_event(service, cal_id, event):
            print(f"  + [{calendar_name}] {event['summary']}")
            created += 1
        else:
            skipped += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}")
