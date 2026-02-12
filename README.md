# Feederr

**Bridge between Sonarr/Radarr/Prowlarr and Unit3D private trackers via Torznab API.**

Feederr exposes a Torznab-compatible API so Unit3D-based private trackers appear as standard indexers to the *arr ecosystem. It handles authentication, session management, title normalization, and torrent downloads automatically.

## Features

- **Torznab API** — Full protocol support (`caps`, `search`, `tvsearch`, `movie`) compatible with Prowlarr, Sonarr, and Radarr
- **Multi-tracker support** — Add and manage multiple Unit3D indexers from the web UI
- **Playwright-based scraper** — Handles sites with Brotli compression or anti-bot measures
- **httpx API scraper** — Faster alternative for sites with standard HTTP responses
- **Download proxy** — Fetches `.torrent` files via browser automation with optional auto-thanks
- **Session management** — Cookie persistence, auto-renewal on expiry detection, daily scheduled renewals (8–9 AM)
- **Spanish title normalization** — Converts "Temporada 1" → S01, handles dual/multi language tags, removes year parentheses for TV matching
- **Time restrictions** — Limit tracker communication to specific hours
- **User-Agent rotation** — Random, indexed, or custom user-agent per indexer
- **Web dashboard** — Manage indexers, view logs, test searches, monitor API status

## Architecture

```
*arr apps ──► Torznab XML API ──► Feederr ──► Playwright/httpx ──► Unit3D trackers
                                     │
                              Download proxy
                                     │
                              .torrent file ──► *arr app
```

## Quick Start (Docker Hub)

To run Feederr using the prebuilt Docker Hub image, use this minimal `docker-compose.yml`:

```yaml
services:
  feederr:
    container_name: feederr
    image: ejejejejejjj/feederr:latest
    restart: unless-stopped
    ports:
      - "9797:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./cookies:/app/cookies
      - ./config:/app/config
    environment:
      APP_NAME: Feederr
      PORT: 9797
      HOST: 0.0.0.0
      BROWSER_HEADLESS: "true"
      BROWSER_TIMEOUT: 30000
      SESSION_REFRESH_HOURS: 24
      LOG_LEVEL: INFO
      TZ: Europe/Madrid
```

Copy this file and launch Feederr with:

```bash
docker compose up -d
```

Access the web UI at `http://localhost:9797` (or your configured port) and add your indexers.

---
## Quick Start (WIN & Linux)

Helper scripts are located in the `scripts/` directory:
- `scripts/setup.bat` — Setup script for Windows
- `scripts/launch.bat` — Launch Feederr as a background service (Windows)
- `scripts/uninstall.bat` — Stop and remove Feederr service and files (Windows)

- `scripts/setup.sh` — Setup script for Linux/macOS
- `scripts/launch.sh` — Launch Feederr as a background service (Linux/macOS)
- `scripts/uninstall.sh` — Stop and remove Feederr service and files (Linux/macOS)

### Example usage

```bash
# Setup (Linux/macOS)
bash scripts/setup.sh
# Launch as background service
bash scripts/launch.sh
# Uninstall
bash scripts/uninstall.sh
```

```bat
REM Setup (Windows)
scripts\setup.bat
REM Launch as background service
scripts\launch.bat
REM Uninstall
scripts\uninstall.bat
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `9797` | Port for the web UI and API |
| `HOST` | `0.0.0.0` | Listen address |
| `APP_NAME` | `Feederr` | Application name |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `BROWSER_HEADLESS` | `true` | Run Chromium in headless mode |
| `BROWSER_TIMEOUT` | `30000` | Browser timeout in ms |
| `SESSION_REFRESH_HOURS` | `24` | Hours before session auto-refresh |
| `TZ` | `Europe/Madrid` | Timezone |

### Indexer Configuration

Indexers are managed through the web UI at `/home`. Each indexer supports:

- **URL** — Tracker base URL
- **Credentials** — Username and password (validated via real login)
- **Enabled/Disabled** — Toggle tracker communication
- **Auto-thanks** — Automatically thank the uploader on download
- **Time restrictions** — Operating hours (e.g., 10:00–23:59)
- **User-Agent** — Random rotation, pick from list, or custom string

### Adding to Prowlarr

1. Open Prowlarr → Settings → Indexers → Add → **Generic Newznab** (or Torznab)
2. Set URL: `http://<your-server-ip>:9797/api/v1/torznab/{indexer_id}`
3. Set API Key: (shown in Feederr's web UI at `/home`)
4. Test and save

## API Reference

### Torznab (for *arr apps)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/torznab/{indexer}?t=caps` | Indexer capabilities |
| `GET /api/v1/torznab/{indexer}?t=search&q=...` | General search |
| `GET /api/v1/torznab/{indexer}?t=tvsearch&q=...&season=X&ep=Y` | TV search |
| `GET /api/v1/torznab/{indexer}?t=movie&q=...` | Movie search |
| `GET /api/v1/download/{indexer}/{torrent_id}` | Download torrent file |

All Torznab endpoints accept `apikey`, `q`, `cat`, `imdbid`, `tmdbid`, `tvdbid`, `season`, `ep`, `limit`, `offset` parameters.

### Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/status` | GET | All indexers status |
| `/api/indexers/list` | GET | List configured indexers |
| `/api/indexers` | POST | Create indexer (validates credentials) |
| `/api/indexers/{id}` | DELETE | Delete indexer + session cookies |
| `/api/indexers/{id}/config` | GET/POST | Get/update indexer config |
| `/api/indexers/{id}/refresh-session` | POST | Force session renewal |
| `/api/regenerate-key` | POST | Regenerate API key |

### Web UI

| Page | Description |
|------|-------------|
| `/home` | Dashboard — indexer management |
| `/home/logs` | Application & network logs |
| `/home/query-builder` | Interactive Torznab search tester |
| `/home/api-status` | Live API status overview |
| `/home/api-docs` | API documentation |

## Project Structure

```
feederr/
├── app/
│   ├── main.py              # FastAPI entry point + lifespan
│   ├── config.py            # Settings (env vars via Pydantic)
│   ├── auth.py              # Playwright authentication manager
│   ├── models.py            # Data models + title normalization
│   ├── indexer_config.py    # Indexer CRUD (JSON persistence)
│   ├── session_scheduler.py # Daily session auto-renewal (8-9 AM)
│   ├── dependencies.py      # FastAPI dependency injection
│   ├── network_logger.py    # HTTP request debug logger
│   ├── api/
│   │   ├── torznab.py       # Torznab XML protocol (core)
│   │   ├── download.py      # Torrent download proxy
│   │   ├── health.py        # Health check endpoints
│   │   └── indexers.py      # Indexer search API
│   ├── scrapers/
│   │   └── unit3d.py        # Unit3D scrapers (Playwright + httpx)
│   ├── templates/           # Jinja2 HTML templates (dashboard)
│   └── web/
│       └── ui.py            # Web UI REST endpoints
├── config/                  # Indexer config (user data, gitignored)
├── cookies/                 # Session cookies (user data, gitignored)
├── data/                    # API key (user data, gitignored)
├── logs/                    # App logs (gitignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── config/indexers.example.json
```

## Requirements

- **Python** 3.11+
- **Playwright** with Chromium
- **Docker** (recommended) or bare metal

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Session expires overnight | Sessions auto-renew daily 8–9 AM. Check logs for renewal errors. |
| Torznab returns empty XML | Verify indexer is enabled and within time restrictions. |
| "Login page detected" in logs | Credentials may have changed. Update via web UI. |
| Download fails | Ensure Playwright can reach the tracker. Check network/cookies. |
| Prowlarr can't connect | Verify the port in `environment` matches your Prowlarr config. Use `http://<server-ip>:<port>`. |

## License

MIT

---

## Special Thanks

Special thanks to Claude for inspiration and assistance during the development of this project.

## Disclaimer

- **This project was generated and assisted in large part by artificial intelligence.**
- **Use of this software may violate the Terms of Service of private trackers or indexers it connects to.**
- **The user is solely responsible for any consequences resulting from the use of this code. Use at your own risk.**

---