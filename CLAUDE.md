# rss-digest

Personal RSS pipeline. Fetches, filters, and publishes RSS feeds to GitHub Pages. Also syncs Songkick events to Google Calendar.

Output feeds are served at `https://justinlycklama.github.io/rss-digest/<filename>.xml`.

**Read [PRINCIPLES.md](PRINCIPLES.md) before changing feeds, sources, or output timing.**

---

## CI Jobs

### Daily RSS Digest — `.github/workflows/daily.yml`
**Schedule:** Daily at 10am UTC (GitHub often starts it hours late)

1. Restores `*_archive.json` from gh-pages
2. Runs `pipeline.py` (all feeds defined in `feeds_config.py`)
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

## Source Inventory

All tracked sources, one row per source. Check `pipeline_status.json` on gh-pages for live health.

### Feed: `toronto_events` → `output/toronto_events.xml`
| Source | Type | URL / Notes |
|---|---|---|
| NowToronto | RSS | `https://nowtoronto.com/events/feed/` |
| MATO | Scraper | `https://ma.to/events/toronto` — JSON-LD on SSR pages; fetches today + next-week listing, skips events <5 days out |
| SharpenSkills | API | `https://sharpenskills.ca` — custom WP REST endpoint (`/wp-json/affutes-acuity/v1/listings`); paginates with `page_num` |
| Monarch Tavern | — | **PENDING** — CSR site backed by Supabase; needs anon API key extracted from DevTools |

### Feed: `toronto_raves` → `output/toronto_raves.xml`
| Source | Type | URL / Notes |
|---|---|---|
| r/TorontoRaves | Reddit | **BROKEN since 2026-11-17 (TODO, parked)**: Reddit returns 404 to anonymous `.rss` from GitHub runners. Fix: Reddit API with app-only OAuth (`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` secrets). User is staying off Reddit for now. |

### Feed: `news` → `output/news.xml`
| Source | Type | URL / Notes |
|---|---|---|
| BBC | RSS | `http://feeds.bbci.co.uk/news/world/rss.xml` |
| Guardian | RSS | `https://www.theguardian.com/world/rss` |
| NYT | RSS | `https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml` |
| CBC Canada | RSS | `https://www.cbc.ca/cmlink/rss-canada` |
| CBC Toronto | RSS | `https://www.cbc.ca/cmlink/rss-canada-toronto` |
| NPR Politics | RSS | `https://feeds.npr.org/1014/rss.xml` |
| The Verge | RSS | `https://www.theverge.com/rss/index.xml` |
| Ars Technica | RSS | `https://feeds.arstechnica.com/arstechnica/index` |
| Spacing Toronto | RSS | `https://spacing.ca/toronto/feed/` |

### Feed: `media_recs` → `output/media_recs.xml`
| Source | Type | URL / Notes |
|---|---|---|
| Reactor Mag | RSS | `https://reactormag.com/feed/` |
| Roger Ebert | RSS | `https://www.rogerebert.com/feed` |
| Eurogamer | RSS | `https://www.eurogamer.net/feed` |
| AV Club | RSS | `https://www.avclub.com/rss` |
| Slant Magazine | RSS | `https://www.slantmagazine.com/feed/` |

### Feed: `fun` → `output/fun.xml`
| Source | Type | URL / Notes |
|---|---|---|
| XKCD | RSS | `https://xkcd.com/rss.xml` |

### Feed: `starcraft` → `output/starcraft.xml`
| Source | Type | URL / Notes |
|---|---|---|
| Blizzard SC2 | API | Custom scraper — `sources/custom/blizzard.py` |

### Feed: `shambhala` → `output/shambhala.xml`
| Source | Type | URL / Notes |
|---|---|---|
| Shambhala Blog | Scraper | Custom scraper — `sources/custom/shambhala.py` |

### Pipeline health
After each run, `output/pipeline_status.json` on gh-pages lists every source, item count, and whether it succeeded. A `count: 0` or `ok: false` row means that source needs attention.

---

## Emergency Rollback

Tag `known-good-2026-11` (commit `6c12331`) is the last state before the Nov 2026 source changes.

- **One-off rebuild with old code:** `gh workflow run daily.yml --ref known-good-2026-11`. The next scheduled run uses `main` again.
- **Stay on old code:** `git revert --no-edit known-good-2026-11..main` then push.
- Archives on gh-pages carry over either way. To start feeds fresh, delete the `*_archive.json` files from gh-pages first.

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
