# 8 Pillars Residential Concrete LeadBot — Final Build

This package is a tested residential-concrete lead discovery and triage system for Aubrey, Little Elm, Prosper, Denton, Frisco, McKinney, and Celina.

## Sources
- Brave Search API: fresh public-web discovery (`pd` first, then `pw` fallback).
- Nextdoor Search Posts API: official OAuth/API access required.
- Authorized IMAP inbox: captures lead marketplace notification emails.
- RSS/Atom feeds.
- JSON drop folder for approved exports/webhooks.

## What it extracts
Publicly supplied poster/contact name when present, phone, email, project address, city, neighborhood, scope, dimensions, approximate square footage, urgency, source link, and source evidence.

## What it does NOT do
It does not reverse-identify private social posters, infer hidden home addresses, bypass login/CAPTCHA/private groups, or scrape against access controls. If a project address is published or voluntarily supplied, it is captured and shown in the dashboard.

## Quick start
1. Python 3.11+
2. `python -m venv .venv`
3. Activate the venv.
4. `pip install -r requirements.txt`
5. `cp .env.example .env`
6. Add `BRAVE_API_KEY`.
7. `python -m unittest discover -s tests -v`
8. `python -m leadbot.main selftest`
9. `python -m leadbot.main scan-now`
10. Dashboard: `uvicorn leadbot.api:app --host 0.0.0.0 --port 8080`
11. 24/7: `python -m leadbot.main watch` or `docker compose up -d`

HOT lead alerts can be sent through SMTP email and/or Twilio SMS when credentials are configured.


## Capture and reminder behavior
- Default live capture interval: **30 minutes** (`SCAN_INTERVAL_SECONDS=1800`).
- Duplicate suppression uses canonical URL, source IDs, and high text similarity. A repeat contractor phone/email alone does **not** hide a different project.
- Every action button in the dashboard (Call, Text, Email, Map, Original Post) records `clicked_at`.
- A `NEW` lead that remains untouched for 48 hours is eligible for a reminder.
- If still untouched, the reminder repeats every 48 hours.
- Changing status to `contacted`, `site_visit`, `quoted`, `won`, `lost`, or `archived` stops untouched reminders.
- Reminder delivery uses the same configured SMTP email and/or Twilio SMS channels as hot-lead alerts.

Useful commands:
- `python -m leadbot.main scan-now` — capture now.
- `python -m leadbot.main watch` — continuously scan every 30 minutes.
- `python -m leadbot.main reminders-now` — process due 48-hour reminders immediately.
- `python -m leadbot.main selftest` — built-in end-to-end test.


## Deep social capture — v3
- **Nextdoor:** official Search Posts API by keyword/geography, with `include_comments=true`; public posts are searched on a 30-minute cycle when approved API credentials are configured.
- **TikTok public requests:** dedicated TikTok-focused fresh web discovery catches publicly indexed videos/captions asking for concrete contractors. TikTok does not provide an unrestricted commercial keyword-search API for every public video; approved TikTok data products have access/use restrictions.
- **TikTok Business DMs:** `/webhooks/tiktok` and `/webhooks/social-dm/tiktok` ingest authorized Business Account message events into the same lead pipeline.
- **Facebook/Instagram business DMs:** `/webhooks/meta` ingests Messenger/Instagram business messaging webhook events.
- **Email fallback:** authorized IMAP ingestion captures marketplace/social notification emails containing concrete/driveway/patio/foundation/message keywords.
- **Deep public-page enrichment:** normal public webpages are fetched for additional published phone/email/project-address evidence. Social-network pages are not bypassed; they use official APIs or public search snippets.

### Contactability rule
HOT alerts are contactable-only by default. A lead is considered contactable when it has a publicly supplied phone/email, is an inbound authorized business DM, or has a direct social post/profile route that lets 8 Pillars message the poster. Leads with no usable contact route can be stored for research but are not pushed as HOT.
