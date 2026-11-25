# Guiding Principles

The point of this pipeline is a calm replacement for social media: a small, trustworthy daily read. Every change should be checked against these.

## 1. Low volume by default
- Budget each feed to a handful of new items per day. A new source must not dominate its feed.
- If a source produces a lot (e.g. SharpenSkills' ~190 workshops), sample it: rotate a category per day, cap items, or raise the lookahead. Don't dump it into the Claude filter and hope.
- Only new items go through Claude. Raw volume is still cost, so trim at the source first.

## 2. An item's date never changes
- An item's `pubDate` (`display_date` in the archive) is set once, when it first enters the archive.
- Never re-date the archive on later runs. Old items must not show up as new again.

## 3. Feeds interleave
- A run's new items are spread across the 24h before the run, alternating between feeds, so no single feed fills the top of the reader.
- Any new output step must keep this. Don't write timestamps that cluster one feed together.

## 4. Removing a source removes its content
- Archive items from sources no longer in `feeds_config.py` are pruned on the next run. If a source is gone from the config, its items are gone from the feed.

## 5. Freshness matches the content
- Archive windows should match how long the content stays useful. Events that have already happened shouldn't stay around. News is stale after days, not months.
- Prefer filtering on the event date over the post date when the source gives one.

## 6. Fail visibly
- Every source has a `name`, and each run records its item count in `pipeline_status.json`.
- A source returning 0 items several days in a row is broken until shown otherwise.
- The Source Inventory in `CLAUDE.md` is updated whenever a source is added, removed, or changes method.

## 7. Source method, in order of preference
1. Official RSS/Atom feed
2. Public JSON/REST API the site itself uses
3. HTML/JSON-LD scraping
- No social media sources (Instagram, etc.). Getting away from them is the reason this project exists.
