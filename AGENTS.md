# AGENTS.md — AI Agent Instructions for Feederr

This file provides context for AI coding agents working on this project.

## Project Overview

Feederr is a **Torznab bridge** that connects *arr apps (Sonarr, Radarr, Prowlarr) to Unit3D-based private torrent trackers. It is written in Python using FastAPI and uses Playwright for browser automation.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI (Python 3.11) | Web framework + async support |
| Browser automation | Playwright (Chromium) | Login, scraping (Torrentland), downloads |
| HTTP client | httpx (HTTP/2) | Scraping (xBytesV2), API calls |
| HTML parsing | BeautifulSoup4 + lxml | Torrent metadata extraction |
| Configuration | Pydantic Settings | Env var management |
| Templates | Jinja2 | Web UI HTML rendering |
| Deployment | Docker + docker-compose | Containerization |

## Architecture

```
main.py                    → FastAPI app, lifespan (startup/shutdown)
├── config.py              → Pydantic Settings (env → Settings object)
├── auth.py                → AuthManager (Playwright login, cookies, sessions)
├── indexer_config.py      → IndexerConfig (JSON CRUD for indexer configs)
├── session_scheduler.py   → Background task: daily session renewal 8-9AM
├── dependencies.py        → FastAPI DI (get_auth_manager singleton)
├── models.py              → SearchRequest, Torrent (title normalization)
├── network_logger.py      → In-memory HTTP request debug log
├── api/
│   ├── torznab.py         → Torznab XML protocol endpoints (core feature)
│   ├── download.py        → Torrent file download proxy via Playwright
│   ├── health.py          → /api/health, /api/status
│   └── indexers.py        → /api/indexers/... (search, refresh)
├── scrapers/
│   └── unit3d.py          → Unit3DScraper (ABC) → TorrentlandScraper, XBytesV2Scraper
├── web/
│   └── ui.py              → Web UI pages + REST API for frontend
└── templates/
    ├── base.html           → Base template (nav, CSS, layout)
    ├── index.html          → Dashboard (indexer cards, add/config modals)
    ├── logs.html           → Log viewer
    ├── query_builder.html  → Search tester
    ├── api_status.html     → API status
    └── api_docs.html       → API docs
scripts/
├── setup.sh               → Setup script (Linux/macOS)
├── setup.bat              → Setup script (Windows)
├── launch.sh              → Launch Feederr as background service (Linux/macOS)
├── launch.bat             → Launch Feederr as background service (Windows)
├── uninstall.sh           → Uninstall script (Linux/macOS)
└── uninstall.bat          → Uninstall script (Windows)
```

## Key Patterns

### Scraper Types

Two scraper implementations inherit from `Unit3DScraper`:

1. **TorrentlandScraper** — Uses Playwright (headless browser) because the site uses Brotli compression that httpx cannot handle. Scrapes HTML table `table.modern-data-table`.

2. **XBytesV2Scraper** — Uses httpx (standard HTTP client). Faster and lighter. Scrapes HTML table `table.data-table` with `tr.torrent-search--list__row`.

Both share the same base class which provides: cookie management, user-agent rotation, random delays, date/size parsing, and login detection.

### Scraper Instantiation

In `torznab.py` and `indexers.py`, scrapers are created dynamically based on `indexer_id`:

```python
if indexer == 'torrentland':
    scraper = TorrentlandScraper(indexer_cfg.get("url"), auth_manager, indexer_cfg)
else:
    scraper = XBytesV2Scraper(indexer_cfg.get("url"), auth_manager, indexer_cfg)
```

When adding new Unit3D trackers: if the site uses Brotli, extend `TorrentlandScraper`; otherwise, extend `XBytesV2Scraper`.

### Authentication Flow

1. `AuthManager.ensure_session(indexer_id)` checks for existing valid cookies
2. If expired or missing, calls `_login_generic()` which uses Playwright to:
   - Navigate to `{url}/login`
   - Fill username/password fields (tries multiple CSS selectors)
   - Submit and wait for redirect
   - Save cookies to `/app/cookies/{indexer_id}_cookies.json`
3. Session expiry is detected during search by `is_login_page()` which checks URL and HTML content
4. On detection, session is auto-renewed and search retried

### Title Normalization

`Torrent.get_title_with_languages()` transforms Spanish tracker titles for *arr compatibility:
- "ESP"/"SPA"/"CAST" → "SPANiSH"
- "Temporada 1" / "Primera temporada" → S01
- Year parentheses `(2023)` removed for TV searches
- Language tags detected and appended

### Session Scheduler

Background asyncio task that:
- Assigns each indexer a random time between 08:00–08:59
- Checks every 30 seconds
- Calls `auth_manager.refresh_session()` at the scheduled time
- Only processes enabled indexers

## Data Flow

### Search Request
```
Prowlarr → GET /api/v1/torznab/{indexer}?t=search&q=...&apikey=...
         → Validate API key
         → Check indexer enabled + time restrictions
         → Create SearchRequest model
         → TorrentlandScraper.search() or XBytesV2Scraper.search()
         → Parse HTML → List[Torrent]
         → Apply title normalization
         → Generate Torznab XML response
         → Return to Prowlarr
```

### Download Flow
```
Sonarr → GET /api/v1/download/{indexer}/{torrent_id}?apikey=...&thanks=true
       → Open Playwright browser with stored cookies
       → Navigate to torrent page
       → Click download button (try multiple selectors)
       → Intercept .torrent file download
       → Optionally click "thanks" button
       → Return .torrent file to Sonarr
```

## File Sensitivity

| Path | Contents | Git Status |
|------|----------|------------|
| `config/indexers.json` | Tracker URLs, usernames, passwords | **gitignored** |
| `data/api_key.txt` | Generated API key | **gitignored** |
| `cookies/*.json` | Session cookies | **gitignored** |
| `logs/app.log` | Application logs | **gitignored** |
| `.env` | Environment variables | **gitignored** |
| `config/indexers.example.json` | Example config (safe) | tracked |
| `.env.example` | Example env (safe) | tracked |

## Common Modification Tasks

### Adding a new Unit3D tracker
1. Decide scraper type (Playwright vs httpx)
2. If the site is similar to existing, just add it via the web UI — no code changes needed
3. If the site has unique HTML structure, create a new class in `unit3d.py`
4. Add instantiation logic in `torznab.py` and `indexers.py`

### Adding new Torznab categories
- Edit `TORZNAB_CAT_MAP` and `_map_torznab_categories()` in `unit3d.py`
- Update `caps` response in `torznab.py`

### Modifying title normalization
- Edit `models.py`, specifically `_transform_spanish_seasons()`, `_remove_year_parentheses()`, and `get_title_with_languages()`
