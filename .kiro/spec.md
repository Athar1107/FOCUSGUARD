# FocusGuard — Master Technical Specification

> This is the single source of truth for building FocusGuard from scratch.
> All other documents (`product.md`, `requirement.md`, `architecture.md`, `tools.md`) are referenced here and provide deeper detail on their respective domains.

---

## 1. Overview

FocusGuard is a Python-based desktop application that passively monitors user activity and detects doomscrolling sessions using three simultaneous signals: active window/URL tracking, keyboard and mouse idle detection, and webcam-based gaze detection. It never interrupts the user during work — it only observes, logs, and presents a daily digest at end of day. Everything runs 100% locally; no data leaves the machine and no webcam footage is ever stored.

See `product.md` for the full product vision, user personas, and success metrics.

---

## 2. System Summary

| Property | Value |
|---|---|
| Language | Python 3.10+ (< 3.13) |
| Platforms | Windows 10+ (64-bit), macOS 12+ |
| Distribution | Standalone binary via PyInstaller — no Python required on user machine |
| UI surface | System tray (primary), Tkinter settings window (on demand), HTML digest (browser) |
| Network | Localhost only (`127.0.0.1:5678`) — no internet required |
| Storage | Single SQLite file in user app data directory |
| ML inference | On-device CPU only — no GPU required |
| Webcam data | Binary gaze result only — no frames, no video, no image files ever stored |

See `tools.md` for full library justifications and version pins.
See `architecture.md` for the component diagram, threading model, and inter-component communication.

---

## 3. Core Detection Logic

### 3.1 The Three-Signal Model

FocusGuard evaluates three independent signals continuously. A doomscroll session is only logged when the signals align according to the rules below.

| Signal | Source | Active State |
|---|---|---|
| Window/URL | `pygetwindow` + `psutil` + browser extension | Distracting site or app is in the foreground |
| Idle | `pynput` keyboard/mouse listener | No input for ≥ `idle_threshold_seconds` (default: 30s) |
| Gaze | OpenCV + MediaPipe Face Mesh | User is looking at the screen (`LOOKING`) |

### 3.2 Session Tiers

**Tier 1 — Unconfirmed**
```
window_signal == DISTRACTING
AND idle_signal == IDLE
AND gaze_signal in (NOT_LOOKING, UNAVAILABLE, TOGGLED_OFF)
```
Logged when the user is on a distracting site with hands idle, but gaze is not confirmed. This covers the case where the webcam is toggled OFF or the user has looked away.

**Tier 2 — Confirmed**
```
window_signal == DISTRACTING
AND idle_signal == IDLE
AND gaze_signal == LOOKING
```
Logged only when all three signals align. This is the definitive doomscroll signal. **Tier 2 sessions cannot be produced without an active, functioning webcam.** This is a hard constraint, not a degraded mode.

> **Webcam gaze detection is a core required feature.** The user controls it via a manual ON/OFF toggle in the system tray, but it is always expected to be ON during work sessions. Toggling it OFF downgrades all detection to Tier 1 only.

### 3.3 Session Start and End

**Session start:** The moment the active tier condition (Tier 1 or Tier 2) first becomes true. A `SessionRecord` is opened with `started_at = UTC now`.

**Session end:** The moment the active tier condition becomes false (any signal breaks). The session is closed with `ended_at = UTC now` and `duration_seconds = ended_at - started_at`.

**Minimum duration filter (open question — see Section 10):** Sessions shorter than a configurable minimum (proposed default: 10 seconds) may be discarded rather than logged to reduce noise. This is not yet decided.

**Tier transition:** If a Tier 1 session is open and the gaze signal changes to `LOOKING`, the Tier 1 session is closed and a new Tier 2 session opens immediately. The two records are stored separately.

### 3.4 Polling Intervals and Thresholds

All values are configurable via `config.json`. These are the defaults:

| Parameter | Default | Config key |
|---|---|---|
| Window poll interval | 2 seconds | `window_poll_interval_seconds` |
| Gaze emit interval | 3 seconds | `gaze_poll_interval_seconds` |
| Idle threshold | 30 seconds | `idle_threshold_seconds` |
| Confirmation window (min session to log) | 120 seconds | `confirmation_window_secs` |
| Gaze detection FPS | 5 FPS | `gaze_fps` |
| Webcam retry interval | 30 seconds | `gaze_retry_interval_secs` |

### 3.5 Default Distracting Sites List

The following domains are blocked by default. The user can add, remove, or disable any entry via the Settings UI.

```
reddit.com
twitter.com
x.com
instagram.com
facebook.com
youtube.com
tiktok.com
news.ycombinator.com
bbc.com
cnn.com
theguardian.com
nytimes.com
dailymail.co.uk
buzzfeed.com
huffpost.com
```

Domain matching is case-insensitive and subdomain-aware: a rule for `reddit.com` matches `www.reddit.com`, `old.reddit.com`, and any other subdomain.

---

## 4. Data Schema

All data is stored in a single SQLite file at:
- **Windows:** `%APPDATA%\focusguard\focusguard.db`
- **macOS:** `~/Library/Application Support/focusguard/focusguard.db`

WAL journal mode is enabled at connection time: `PRAGMA journal_mode=WAL`.

### 4.1 `sessions` table

Stores every detected session — both confirmed and unconfirmed. Records are append-only and must never be modified or deleted after writing.

```sql
CREATE TABLE sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT    NOT NULL,  -- ISO 8601 UTC, e.g. "2024-11-15T14:22:00Z"
    ended_at         TEXT    NOT NULL,  -- ISO 8601 UTC
    duration_seconds INTEGER NOT NULL,  -- ended_at - started_at in whole seconds
    site             TEXT    NOT NULL,  -- matched domain (e.g. "reddit.com") or app name
    app_name         TEXT    NOT NULL,  -- process name of the foreground window
    tier             TEXT    NOT NULL,  -- "confirmed" | "unconfirmed"
    signals_triggered TEXT   NOT NULL,  -- JSON: {"window":1,"idle":1,"gaze":1}
    gaze_status      TEXT    NOT NULL   -- "LOOKING" | "NOT_LOOKING" | "UNAVAILABLE" | "TOGGLED_OFF"
);
```

### 4.2 `sites` table

Mirrors the distracting sites/apps list from `config.json`. Kept in sync on every settings save. Used by the Report Generator for category-level aggregation.

```sql
CREATE TABLE sites (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    domain       TEXT    NOT NULL UNIQUE,  -- e.g. "reddit.com" or app name
    category     TEXT    NOT NULL,         -- "social" | "news" | "video" | "app" | "custom"
    date_added   TEXT    NOT NULL,         -- ISO 8601 date, e.g. "2024-11-01"
    enabled      INTEGER NOT NULL DEFAULT 1
);
```

### 4.3 `config` table

Stores a snapshot of the active configuration at the time of each app launch. Used for debugging and audit — the live config is always read from `config.json`.

```sql
CREATE TABLE config (
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,  -- ISO 8601 UTC
    PRIMARY KEY (key)
);
```

### 4.4 `daily_summaries` table

Pre-aggregated per-day totals. Updated by the Session Manager each time a session is written. Enables fast report generation without full table scans.

```sql
CREATE TABLE daily_summaries (
    date                     TEXT    PRIMARY KEY,  -- "YYYY-MM-DD"
    confirmed_count          INTEGER NOT NULL DEFAULT 0,
    confirmed_duration_secs  INTEGER NOT NULL DEFAULT 0,
    unconfirmed_count        INTEGER NOT NULL DEFAULT 0,
    unconfirmed_duration_secs INTEGER NOT NULL DEFAULT 0,
    top_sites                TEXT                   -- JSON: [{"site":"reddit.com","duration_secs":480}, ...]
);
```

---

## 5. API Contracts

### 5.1 Browser Extension → Flask Server

The browser extension POSTs to the local Flask server whenever the active tab URL changes.

**Endpoint:** `POST http://127.0.0.1:5678/url`

**Request body (JSON):**
```json
{
  "url": "https://www.reddit.com/r/programming/",
  "timestamp": "2024-11-15T14:22:03Z",
  "browser": "chrome"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | Full URL of the active tab including scheme |
| `timestamp` | string | Yes | ISO 8601 UTC timestamp from the browser |
| `browser` | string | Yes | Browser identifier: `"chrome"`, `"edge"`, `"firefox"` |

**Response body (JSON):**
```json
{
  "status": "logged",
  "tier": "distracting"
}
```

| Field | Values | Description |
|---|---|---|
| `status` | `"logged"` \| `"ignored"` | Whether the URL was accepted and forwarded |
| `tier` | `"distracting"` \| `"clean"` | Whether the URL matched the distracting sites list |

**Error responses:**

| HTTP status | Condition |
|---|---|
| `400 Bad Request` | Missing or malformed `url` or `timestamp` field |
| `405 Method Not Allowed` | Non-POST request to `/url` |

**Health check endpoint:** `GET http://127.0.0.1:5678/ping`

Response: `{ "status": "ok" }` with HTTP 200. Used by the browser extension to verify the local server is running.

### 5.2 Security constraints

- The Flask server MUST bind to `127.0.0.1` only — never `0.0.0.0`.
- Requests from any IP other than `127.0.0.1` MUST be rejected with HTTP 403.
- The server does not use authentication tokens. Security relies entirely on the localhost binding.

---

## 6. File Structure

```
focusguard/                          # Project root / PyInstaller bundle root
│
├── main.py                          # Entry point: loads config, inits all components, starts tray
├── config.json                      # Default config (copied to user data dir on first run)
├── requirements.txt                 # Pinned runtime dependencies
├── requirements-dev.txt             # Adds PyInstaller for packaging
│
├── core/
│   ├── session_manager.py           # Three-signal state machine and session lifecycle
│   ├── database_layer.py            # All SQLite reads and writes — no other file touches the DB
│   └── event_types.py               # Signal constants, SessionRecord dataclass, enums
│
├── detectors/
│   ├── activity_monitor.py          # pygetwindow + psutil window polling (2s interval)
│   ├── idle_detector.py             # pynput global keyboard/mouse listener
│   └── gaze_detector.py             # OpenCV + MediaPipe Face Mesh — CORE COMPONENT
│
├── bridge/
│   ├── flask_server.py              # Flask app: POST /url, GET /ping
│   └── url_state.py                 # Thread-safe shared variable for latest browser URL
│
├── ui/
│   ├── tray_controller.py           # pystray icon, menu, lifecycle orchestration
│   └── settings_window.py           # Tkinter settings UI — reads/writes config.json
│
├── reporting/
│   ├── report_generator.py          # Queries DB, renders Jinja2 template, opens browser
│   └── templates/
│       └── digest.html.j2           # Daily digest HTML template
│
├── assets/
│   ├── chart.min.js                 # Bundled Chart.js 3.4.x — no CDN dependency
│   └── icons/
│       ├── tray_active.png          # Tray icon: gaze detection ON
│       ├── tray_inactive.png        # Tray icon: gaze detection OFF
│       └── tray_error.png           # Tray icon: webcam error state
│
├── extension/                       # Browser extension (distributed separately)
│   ├── manifest.json                # Manifest V3
│   ├── background.js                # Service worker: tab URL monitoring + POST to Flask
│   ├── config.js                    # Extension config: port number
│   └── icons/
│
└── tests/
    ├── test_session_manager.py      # Unit tests: signal logic, tier classification, edge cases
    ├── test_activity_monitor.py     # Unit tests: domain matching, window title fallback
    ├── test_idle_detector.py        # Unit tests: threshold logic, state transitions
    ├── test_gaze_detector.py        # Unit tests: EAR calculation, unavailability handling
    ├── test_database_layer.py       # Unit tests: schema, write/read, WAL mode
    └── test_report_generator.py     # Unit tests: template rendering, data aggregation
```

**User data directory** (created on first run, never bundled):

```
{user_app_data}/focusguard/
├── focusguard.db                    # SQLite database — all session history
├── config.json                      # Live user config (written by Settings UI)
├── focusguard.log                   # Internal error log (rotating, max 5 MB)
└── reports/
    ├── digest_2024-11-14.html
    └── digest_2024-11-15.html
```

**Why this structure:**
- `core/` contains the only stateful logic — everything else is I/O or UI
- `detectors/` are all stateless signal emitters; they call into `core/session_manager`
- `bridge/` is isolated so the Flask server can be tested independently of detection logic
- `ui/` components never call into `core/` directly — they communicate via config file and tray callbacks
- `tests/` mirrors the source tree one-to-one for discoverability

---

## 7. Configuration

All configuration lives in a single `config.json` file in the user data directory. The Settings UI is the only writer. All components read config at startup and re-read on each poll cycle to pick up changes without restart.

Config is written atomically: write to `config.json.tmp`, then rename to `config.json`.

### Full config schema with defaults

```json
{
  "distracting_sites": [
    "reddit.com", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "youtube.com", "tiktok.com",
    "news.ycombinator.com", "bbc.com", "cnn.com",
    "theguardian.com", "nytimes.com", "dailymail.co.uk",
    "buzzfeed.com", "huffpost.com"
  ],
  "distracting_apps": [],

  "idle_threshold_seconds": 30,
  "window_poll_interval_seconds": 2,
  "gaze_poll_interval_seconds": 3,
  "confirmation_window_secs": 120,

  "work_hours_start": "09:00",
  "work_hours_end": "18:00",

  "webcam_enabled": true,
  "webcam_device_index": 0,
  "gaze_fps": 5,
  "gaze_retry_interval_secs": 30,

  "flask_port": 5678,
  "end_of_day_time": "17:30",
  "launch_at_startup": true
}
```

### Config key reference

| Key | Type | Default | Description |
|---|---|---|---|
| `distracting_sites` | string[] | See above | Domains that trigger the window signal |
| `distracting_apps` | string[] | `[]` | Process names that trigger the window signal |
| `idle_threshold_seconds` | int | `30` | Seconds of no input before idle signal activates. Min: 10, Max: 300 |
| `window_poll_interval_seconds` | int | `2` | How often Activity Monitor polls the active window |
| `gaze_poll_interval_seconds` | int | `3` | How often Gaze Detector emits a result to Session Manager |
| `confirmation_window_secs` | int | `120` | Minimum session duration to log. Min: 30, Max: 600 |
| `work_hours_start` | string | `"09:00"` | Start of work hours for digest scheduling (HH:MM, local time) |
| `work_hours_end` | string | `"18:00"` | End of work hours (HH:MM, local time) |
| `webcam_enabled` | bool | `true` | Whether gaze detection starts ON at launch. Core feature — expected to be true |
| `webcam_device_index` | int | `0` | OpenCV device index for webcam selection |
| `gaze_fps` | int | `5` | Webcam capture rate for gaze detection |
| `gaze_retry_interval_secs` | int | `30` | How often to retry webcam acquisition after failure |
| `flask_port` | int | `5678` | Port for the local browser extension bridge server |
| `end_of_day_time` | string | `"17:30"` | Time to auto-generate and notify the daily digest (HH:MM, local time) |
| `launch_at_startup` | bool | `true` | Whether to register FocusGuard in OS startup |

---

## 8. Edge Cases & Error Handling

### 8.1 Webcam unavailable or permission denied

**Trigger:** `cv2.VideoCapture(device_index).isOpened()` returns `False` at startup or during a session.

**Behavior:**
1. Gaze Detector emits `gaze_signal = UNAVAILABLE` to Session Manager
2. Session Manager: Tier 2 (confirmed) sessions cannot be opened or continued. Any open Tier 2 session is closed and written as `unconfirmed`
3. Tier 1 (unconfirmed) detection continues normally using the window and idle signals
4. System Tray Controller updates the tray icon to the error state (`tray_error.png`) and sets the tooltip to: `"FocusGuard: Webcam unavailable — gaze detection paused. Click to open settings."`
5. Gaze Detector retries acquisition every `gaze_retry_interval_secs` seconds
6. On successful re-acquisition: tray icon reverts to active state, Tier 2 detection resumes, no user action required

**What does NOT happen:** The app does not crash, exit, show a modal dialog, or block the user in any way.

### 8.2 Browser extension not installed

**Trigger:** No `POST /url` requests received within 10 seconds of a browser window becoming active.

**Behavior:**
1. Activity Monitor falls back to window title parsing for browser URL detection
2. Window title heuristic: extract domain from titles matching the pattern `"<Page Title> - <Browser Name>"` (e.g., `"Reddit - Google Chrome"`)
3. Accuracy is lower than the extension — subdomain and path information is unavailable
4. No error is shown to the user; this is a graceful degradation
5. The Flask server continues running so the extension can connect at any time without restart

### 8.3 App crash or force-quit mid-session

**Trigger:** Process terminates unexpectedly while a `SessionRecord` is open (i.e., `active_session` is not `None` in Session Manager state).

**Behavior on restart:**
1. On startup, Database Layer queries for any session with a `started_at` but no `ended_at` (orphaned open sessions)
2. For each orphaned session: set `ended_at = started_at + last_known_duration` (estimated from the last DB write timestamp), set `tier = "unconfirmed"`, add a note in `signals_triggered`: `{"recovered": true}`
3. This ensures no session record is left in a partial state

**Prevention:** Session Manager writes a heartbeat timestamp to the `config` table every 30 seconds. On restart, this timestamp is used to estimate the end time of any orphaned session.

### 8.4 Multiple monitors

**Behavior:** FocusGuard tracks only the focused (foreground) window, regardless of which monitor it is on. `pygetwindow.getActiveWindow()` returns the window that has keyboard focus — this is the correct signal for doomscrolling detection. Content on secondary monitors that is not in focus is not tracked.

### 8.5 Webcam in use by another application

**Trigger:** `cv2.VideoCapture` fails because the webcam device is locked by another process (e.g., a video call app).

**Behavior:** Treated identically to webcam unavailable (Section 8.1). The retry loop will re-acquire the webcam once the other application releases it.

### 8.6 Flask port already in use

**Trigger:** `flask_port` (default: 5678) is occupied by another process at startup.

**Behavior:**
1. Flask server logs the error to `focusguard.log`
2. System Tray Controller shows a tray notification: `"FocusGuard: Port 5678 in use — browser URL tracking unavailable. Change port in settings."`
3. App continues running with window title fallback for browser detection (same as Section 8.2)

### 8.7 Config file missing or corrupt

**Trigger:** `config.json` is absent, empty, or contains invalid JSON at startup.

**Behavior:**
1. App logs the error and writes a fresh `config.json` with all defaults
2. User's previous custom settings are lost — this is acceptable given the low stakes of config data
3. A tray notification informs the user: `"FocusGuard: Config reset to defaults."`

### 8.8 Database file locked or corrupt

**Trigger:** SQLite returns an error on connection or write.

**Behavior:**
1. Database Layer logs the full error to `focusguard.log`
2. Session Manager buffers up to 50 session records in memory
3. Database Layer retries the write every 5 seconds
4. If the database remains unavailable for more than 5 minutes, a tray notification is shown: `"FocusGuard: Database error — sessions may not be saved. Check focusguard.log."`
5. App does not crash

---

## 9. Out of Scope (v1)

The following are explicitly excluded from the v1 implementation. They are documented here to prevent scope creep and to record the rationale.

| Feature | Rationale for exclusion |
|---|---|
| Cloud sync or remote storage | Contradicts the core privacy guarantee; adds infrastructure complexity |
| Mobile app | Different platform, different detection model; separate product effort |
| Hard site blocking | Changes the product from observer to enforcer — different UX contract |
| Real-time alerts or pop-ups | Directly violates the zero-interruption design principle |
| ML model training | v1 uses MediaPipe's pre-trained Face Mesh; custom model training is a Phase 5 consideration |
| Email or export of reports | Reports are local HTML files; export is a convenience feature, not core |
| Multi-user or team features | FocusGuard is a personal tool; organizational features require a different architecture |
| Firefox extension support | Chrome/Edge (MV3) covers the primary user base; Firefox is a SHOULD for v2 |
| GPU-accelerated inference | CPU-only is sufficient for 5 FPS gaze detection; GPU adds packaging complexity |
| Accessibility API-based URL tracking (no extension) | The browser extension is the authoritative URL source; accessibility APIs are a fallback only |

---

## 10. Open Questions

These questions are unresolved as of the current spec version. Each must be answered before the affected component is implemented.

**Q1 — Minimum session duration threshold**
Should confirmed and unconfirmed sessions below a minimum duration (e.g., < 10 seconds) be discarded rather than logged? A 3-second glance at Reddit while the idle timer happens to be active would currently produce a session record. Proposed resolution: add a `min_session_duration_seconds` config key (default: 10) and discard sessions shorter than this threshold before writing to the DB.

**Q2 — Browser extension scope: Chrome only or Chrome + Firefox?**
The current spec targets Chrome and Edge (Manifest V3). Firefox uses a different extension signing and distribution process. Given that Chrome/Edge covers the majority of the target user base, Firefox support is deferred to v2 unless user research indicates otherwise.

**Q3 — Weekly report as email**
Should the weekly trend report be optionally emailable to the user (e.g., via a local SMTP relay or mailto: link)? This would require no external service — a `mailto:` link with the report attached, or a local SMTP call. Deferred to v2; noted here because the Report Generator's template structure should not preclude it.

**Q4 — Gaze detection accuracy calibration**
The current gaze model uses fixed EAR and iris offset thresholds. Should v1 include a brief per-user calibration step (e.g., "look at the screen for 5 seconds, then look away") to tune these thresholds to the individual user's face geometry and webcam angle? This would improve accuracy but adds onboarding friction. Proposed resolution: ship with conservative fixed thresholds in v1; add optional calibration in v2.

**Q5 — Session tier upgrade/downgrade**
If a Tier 1 session is open and the gaze signal changes to `LOOKING`, the current spec closes the Tier 1 session and opens a new Tier 2 session. An alternative is to upgrade the existing session record in place. The append-only constraint (FR-4.2.3) argues for the close-and-open approach. Confirm before implementing Session Manager.

---

## 11. Document Index

| Document | Purpose |
|---|---|
| `product.md` | Vision, goals, non-goals, user personas, success metrics |
| `requirement.md` | Full functional and non-functional requirements (MUST/SHOULD/MAY) |
| `architecture.md` | Component diagram, threading model, data flow, inter-component communication |
| `tools.md` | Library justifications, alternatives considered, version pins, `requirements.txt` |
| `spec.md` | This document — master technical specification tying all of the above together |
