# rss-digest

Personal RSS pipeline. Fetches, filters, and publishes RSS feeds to GitHub Pages. Also syncs Songkick events to Google Calendar.

Output feeds are served at `https://justinlycklama.github.io/rss-digest/<filename>.xml`.

---

## CI Jobs

### Daily RSS Digest — `.github/workflows/daily.yml`
**Schedule:** Daily at noon UTC (8am EDT)

Runs the full RSS pipeline in order:
1. `run_generate_reddit_rss.py` — generates subreddit feeds
2. `run_custom_scrapers.py` — runs all scrapers in `custom_scrapers/`
3. Deploys everything in `output/` to the `gh-pages` branch

**Secrets required:** `ANTHROPIC_API_KEY`, `NOTION_TOKEN`

---

### Songkick Calendar Sync — `.github/workflows/songkick.yml`
**Schedule:** Every Monday at 10am UTC

Fetches the Songkick iCal feed for tracked artists and creates new events in the *Potential Shows* Google Calendar. Skips events already created (deduped via Google Calendar extended properties).

**Secrets required:** `GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET`, `GCAL_REFRESH_TOKEN`

---

## Pipelines

### News Digest — `custom_scrapers/news_digest.py`
**Output:** `output/news.xml`

Fetches RSS feeds from BBC, Guardian, NYT, CBC Canada, CBC Toronto, NPR Politics, The Verge, Ars Technica. Sends batches of headlines to Claude Haiku for INCLUDE/EXCLUDE decisions. Filter rules are pulled live from the **News Filter Memory** Notion page before each run (page ID: `33ba1339f88a81799204f8b0d4a1ca71`) — editing that page changes filter behaviour without touching code.

Maintains a rolling 7-day archive in `output/news_archive.json` (persisted on gh-pages) so already-filtered articles aren't re-evaluated.

To tune the filter: open the "News Feedback" claude.ai project on mobile or desktop, describe what felt off, Claude proposes and writes updates back to Notion.

---

### Subreddit Feeds — `generate_subreddit_rss.py` + `subreddit_list.txt`
**Output:** `output/<subreddit>.xml` per subreddit

Subreddits are configured in `subreddit_list.txt`, one per line, pipe-delimited:
```
SubredditName | Filter intent for Claude
```

For each subreddit: fetches recent posts, sends them to Claude Haiku with the per-subreddit filter intent, outputs only included posts as RSS.

Orchestrated by `run_generate_reddit_rss.py`.

**Current subreddits:**
- `TorontoRaves` — local Toronto rave/party events with date/venue
- `patientgamers`, `fantasy`, `scifi`, `criterion`, `truefilm`, `booksuggestions`, `televisionsuggestions` — recommendation-focused posts only (for the Media Recommendation Engine)

---

### Media Recommendations — `custom_scrapers/media_recs.py`
**Output:** `output/media_recs.xml`

Fetches Substack newsletters (GriersonLeitch, TheReveal, AnneHelen), filters via Claude for recommendation-focused content (film/book/TV recs), excludes news and announcements.

---

### StarCraft Patches — `custom_scrapers/starcraft_patches.py`
**Output:** `output/starcraft_patches.xml`

Fetches StarCraft II news from Blizzard's API.

---

### Shambhala — `custom_scrapers/shambhala.py`
**Output:** `output/shambhala.xml`

Scrapes the Shambhala Music Festival blog.

---

### Songkick → Google Calendar — `songkick_calendar.py`
**Not part of the daily RSS pipeline** — runs via its own weekly workflow.

Fetches `http://www.songkick.com/users/justin-lycklama/calendars.ics`, parses VEVENT blocks, and creates events in the *Potential Shows* Google Calendar for anything within the next 180 days not already added.

To generate new OAuth tokens: copy `client_secret.json` (from Google Cloud Console) to the repo root and run `python get_calendar_token.py`. Store the output as GitHub secrets.

---

## Local Development

Run the full pipeline locally with:
```powershell
python launcher.py
```

Or run individual pieces:
```powershell
python run_generate_reddit_rss.py
python run_custom_scrapers.py
python songkick_calendar.py
```

Env vars needed locally:
```powershell
$env:ANTHROPIC_API_KEY = "..."
$env:NOTION_TOKEN = "..."
$env:GCAL_CLIENT_ID = "..."
$env:GCAL_CLIENT_SECRET = "..."
$env:GCAL_REFRESH_TOKEN = "..."
```
