# FocusGuard — System Architecture

## Overview

FocusGuard is a single-process, multi-threaded desktop application. All components run within one Python process, communicating via an in-process event bus and shared state objects. The only inter-process communication is the HTTP bridge between the browser extension and the local Flask server.

The application has no network dependencies beyond localhost. All data is stored on-device in a single SQLite file. No background services, daemons, or cloud endpoints are involved.

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FocusGuard Process                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │               System Tray Controller (pystray)               │   │
│  │  - App entry point & lifecycle manager                       │   │
│  │  - Orchestrates component start/stop                         │   │
│  │  - Exposes: webcam toggle, open report, settings, quit       │   │
│  └───────┬──────────────────────────────────────────────────────┘   │
│          │ starts / stops / signals                                  │
│          ▼                                                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Session Manager                          │  │
│  │  - Receives signal events from all detectors                  │  │
│  │  - Applies three-signal confirmation logic                    │  │
│  │  - Opens, tracks, and closes session records                  │  │
│  │  - Writes confirmed/unconfirmed sessions to Database Layer    │  │
│  └──────┬──────────────────────────────────────────────────────-┘  │
│         │ reads/writes                                              │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Database Layer                          │   │
│  │                  (sqlite3 — local .db file)                  │   │
│  │  Tables: sessions, sites, daily_summaries                    │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
│                             │ reads                                 │
│                             ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Report Generator                          │   │
│  │              (Jinja2 templates + Chart.js)                   │   │
│  │  - Generates daily HTML digest and weekly trend report       │   │
│  │  - Opens in default browser on demand or at end-of-day      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Activity Monitor │  │  Idle Detector   │  │  Gaze Detector  │  │
│  │ (pygetwindow +   │  │    (pynput)      │  │ (OpenCV +       │  │
│  │  psutil)         │  │                  │  │  MediaPipe)     │  │
│  │                  │  │                  │  │  CORE FEATURE   │  │
│  │ Polls every 2s   │  │ Event-driven     │  │ Runs at 5 FPS   │  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬─────────┘  │
│           │                     │                     │            │
│           └─────────────────────┴─────────────────────┘            │
│                                 │ signal events                     │
│                                 ▼                                   │
│                         Session Manager                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Browser Extension Bridge                        │   │
│  │         Flask server on 127.0.0.1:5678                      │   │
│  │  - Receives POST /url from browser extension                 │   │
│  │  - Forwards URL signal to Session Manager                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Settings UI                             │   │
│  │                       (Tkinter)                              │   │
│  │  - Reads/writes config.json                                  │   │
│  │  - Opened on demand from system tray                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │                  Browser Extension                           │
  │  (Chrome / Edge — Manifest V3)                               │
  │  - Monitors active tab URL                                   │
  │  - POSTs to http://127.0.0.1:5678/url on tab change         │
  └──────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. System Tray Controller

**Technology:** `pystray`
**Thread:** Main thread

The System Tray Controller is the application entry point. It initializes all components, manages the application lifecycle, and is the only component the user directly interacts with during a work session.

**Responsibilities:**
- Parse `config.json` and make the config object available to all components at startup
- Instantiate and start all detector threads and the Flask server thread
- Instantiate the Session Manager and pass it references to the Database Layer
- Expose the system tray menu with the following actions:
  - Webcam gaze detection ON/OFF toggle (updates config and signals Gaze Detector)
  - Open today's digest (triggers Report Generator)
  - Open settings (opens Tkinter Settings UI)
  - Quit (gracefully shuts down all threads and exits)
- Display system tray status indicators: gaze detection state, webcam error state
- Receive error signals from the Gaze Detector and update the tray icon/tooltip accordingly

**Lifecycle management:**
```
startup:
  load config.json
  init DatabaseLayer
  init SessionManager(db)
  init ActivityMonitor(config, session_manager)
  init IdleDetector(config, session_manager)
  init GazeDetector(config, session_manager)   ← always instantiated
  init BrowserExtensionBridge(config, session_manager)
  start all component threads
  run pystray icon (blocks main thread)

shutdown (on quit):
  signal all threads to stop
  join all threads
  close database connection
  exit
```

---

### 2. Activity Monitor

**Technology:** `pygetwindow`, `psutil`
**Thread:** Dedicated background thread
**Communication:** Calls `session_manager.on_window_signal(state)` directly

The Activity Monitor polls the operating system for the currently active foreground window and determines whether it matches a distracting site or application.

**Responsibilities:**
- Poll the active window title and process name every 2 seconds
- For browser windows: use the URL most recently received from the Browser Extension Bridge as the authoritative source; fall back to window title parsing if no URL has been received within the last 5 seconds
- Compare the active window/URL against the distracting sites/apps list from config
- Emit a `DISTRACTING` or `NEUTRAL` window signal to the Session Manager on each poll

**Signal emission:**
```python
# Called every 2 seconds
session_manager.on_window_signal(
    state="DISTRACTING" | "NEUTRAL",
    site_or_app="reddit.com" | "Slack" | ...,
    source="url" | "window_title"
)
```

---

### 3. Browser Extension Bridge

**Technology:** `Flask` (local HTTP server), custom browser extension (Manifest V3)
**Thread:** Dedicated background thread (Flask dev server with threading=False)
**Communication:** Flask endpoint → calls `session_manager.on_url_received(url)` directly

The Browser Extension Bridge is a two-part component: a lightweight browser extension that monitors the active tab URL, and a local Flask server that receives those URLs.

**Flask server:**
- Binds exclusively to `127.0.0.1:5678` (port configurable)
- Exposes two routes:
  - `POST /url` — receives `{ "url": "https://...", "browser": "chrome" }`, validates input, forwards to Session Manager
  - `GET /ping` — health check for the browser extension to verify the server is running
- Runs in a daemon thread; does not block the main thread

**Browser extension:**
- Background service worker monitors `chrome.tabs.onActivated` and `chrome.tabs.onUpdated`
- On tab change or URL change, POSTs the new URL to `http://127.0.0.1:5678/url`
- Polls `GET /ping` on startup; shows a warning badge if the local server is unreachable

**URL forwarding to Activity Monitor:**
The Flask handler writes the received URL to a thread-safe shared variable that the Activity Monitor reads on its next poll cycle. This avoids direct cross-thread calls into the Session Manager from the Flask thread.

---

### 4. Idle Detector

**Technology:** `pynput`
**Thread:** Dedicated background thread (pynput runs its own listener threads internally)
**Communication:** Calls `session_manager.on_idle_signal(state)` directly

The Idle Detector listens for keyboard and mouse events globally and tracks the elapsed time since the last input event.

**Responsibilities:**
- Register global keyboard and mouse listeners via `pynput.keyboard.Listener` and `pynput.mouse.Listener`
- Record the timestamp of every input event
- On a 1-second evaluation tick, compare `now - last_input_time` against the configured idle threshold (default: 30 seconds)
- Emit `IDLE` when the threshold is exceeded; emit `ACTIVE` when input is detected after an idle period
- Emit state changes only (not on every tick) to avoid flooding the Session Manager

**Signal emission:**
```python
session_manager.on_idle_signal(state="IDLE" | "ACTIVE")
```

---

### 5. Gaze Detector

**Technology:** `OpenCV` (`opencv-python-headless`), `MediaPipe` Face Mesh
**Thread:** Dedicated background thread
**Communication:** Calls `session_manager.on_gaze_signal(state)` directly

> The Gaze Detector is a **core required component**. It is always instantiated. The ON/OFF toggle controls whether the webcam capture loop is running, not whether the component exists.

**Responsibilities:**
- Acquire the webcam device specified in config (default: device index 0)
- Capture frames at the configured rate (default: 5 FPS; only 1 in N frames is processed to reduce CPU load)
- For each processed frame:
  1. Pass the frame to MediaPipe Face Mesh
  2. Extract eye landmark positions (landmarks 33, 133, 362, 263 and iris landmarks 468–472)
  3. Calculate Eye Aspect Ratio (EAR) and iris center offset relative to eye corners
  4. Classify result as `LOOKING` or `NOT_LOOKING`
  5. Discard the frame immediately — no frame data is retained
- Emit the binary gaze result to the Session Manager every 3 seconds (configurable)
- Handle webcam unavailability:
  - On acquisition failure: emit `UNAVAILABLE` to Session Manager, signal System Tray Controller to show error indicator
  - Retry webcam acquisition every 30 seconds (configurable)
  - On successful re-acquisition: resume normal operation, signal System Tray Controller to clear error

**Toggle behavior:**
- When toggled OFF: exit the capture loop, release the webcam (`cap.release()`), emit `TOGGLED_OFF` to Session Manager
- When toggled ON: re-enter the capture loop, re-acquire the webcam

**Signal emission:**
```python
session_manager.on_gaze_signal(
    state="LOOKING" | "NOT_LOOKING" | "UNAVAILABLE" | "TOGGLED_OFF"
)
```

**Privacy guarantee:** The frame buffer is a single `numpy.ndarray` allocated per frame and overwritten on the next capture. No frame is written to disk, passed to any other component, or held in any queue or cache.

---

### 6. Session Manager

**Technology:** Pure Python, thread-safe state machine
**Thread:** Runs logic on the calling thread of each signal emitter (all calls are fast and non-blocking); maintains internal state protected by a `threading.Lock`
**Communication:** Receives direct method calls from all detectors; calls `database_layer.write_session()` to persist

The Session Manager is the core logic component. It maintains the current state of all three signals and applies the confirmation model to determine when a doomscroll session starts and ends.

**Internal state:**
```python
state = {
    "window_signal":  "DISTRACTING" | "NEUTRAL",
    "idle_signal":    "IDLE" | "ACTIVE",
    "gaze_signal":    "LOOKING" | "NOT_LOOKING" | "UNAVAILABLE" | "TOGGLED_OFF",
    "active_session": None | SessionRecord,
    "session_start":  None | datetime,
}
```

**Confirmation logic:**

```
confirmed_condition  = window_signal == DISTRACTING
                     AND idle_signal == IDLE
                     AND gaze_signal == LOOKING

unconfirmed_condition = window_signal == DISTRACTING
                      AND idle_signal == IDLE
                      AND gaze_signal in (NOT_LOOKING, UNAVAILABLE, TOGGLED_OFF)
```

**Session lifecycle:**
1. On each signal update, re-evaluate the current condition
2. If `confirmed_condition` becomes true and no session is open → start a new session record, record `session_start = now`
3. If `confirmed_condition` remains true and a session is open → update `current_duration = now - session_start`
4. If `confirmed_condition` becomes false and a session is open:
   - If `current_duration >= confirmation_window` (default: 2 minutes) → write session as `confirmed` to Database Layer
   - Else → write session as `unconfirmed` to Database Layer
   - Clear active session state
5. `unconfirmed_condition` follows the same open/close logic but always writes as `unconfirmed`

**Thread safety:** All state reads and writes are wrapped in a `threading.Lock`. Signal handler methods acquire the lock, update state, evaluate conditions, and release the lock. Lock hold time is kept under 1ms.

---

### 7. Database Layer

**Technology:** Python `sqlite3` (stdlib)
**Thread:** Called from Session Manager thread and Report Generator; uses WAL journal mode for concurrent reads
**Storage:** Single `.db` file at `{user_app_data}/focusguard/focusguard.db`

The Database Layer provides a simple read/write interface over the local SQLite database. It is the only component that touches the `.db` file directly.

**Schema:**

```sql
-- All detected doomscroll sessions (confirmed and unconfirmed)
CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,          -- ISO 8601 UTC
    ended_at        TEXT NOT NULL,          -- ISO 8601 UTC
    duration_secs   INTEGER NOT NULL,
    site_or_app     TEXT NOT NULL,
    classification  TEXT NOT NULL,          -- 'confirmed' | 'unconfirmed'
    window_signal   INTEGER NOT NULL,       -- 1 = active, 0 = not
    idle_signal     INTEGER NOT NULL,
    gaze_signal     INTEGER NOT NULL,
    gaze_status     TEXT NOT NULL           -- 'LOOKING' | 'NOT_LOOKING' | 'UNAVAILABLE' | 'TOGGLED_OFF'
);

-- Configurable distracting sites and apps (mirrors config.json, kept in sync)
CREATE TABLE sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT NOT NULL UNIQUE,       -- domain or app name
    type        TEXT NOT NULL,              -- 'domain' | 'app'
    enabled     INTEGER NOT NULL DEFAULT 1
);

-- Pre-aggregated daily summaries for fast report generation
CREATE TABLE daily_summaries (
    date                    TEXT PRIMARY KEY,   -- YYYY-MM-DD
    confirmed_count         INTEGER NOT NULL DEFAULT 0,
    confirmed_duration_secs INTEGER NOT NULL DEFAULT 0,
    unconfirmed_count       INTEGER NOT NULL DEFAULT 0,
    top_sites               TEXT                -- JSON array of {site, duration_secs}
);
```

**WAL mode:** Enabled at connection time (`PRAGMA journal_mode=WAL`) to allow the Report Generator to read while the Session Manager writes.

**Interface:**
```python
db.write_session(session: SessionRecord) -> None
db.get_sessions_for_date(date: str) -> list[SessionRecord]
db.get_daily_summary(date: str) -> DailySummary
db.get_weekly_summaries(end_date: str) -> list[DailySummary]
```

---

### 8. Report Generator

**Technology:** `Jinja2`, `Chart.js` (bundled static asset)
**Thread:** Runs on demand in the calling thread (fast; reads from DB and renders template)
**Communication:** Reads from Database Layer; opens rendered HTML file in default browser

The Report Generator queries the Database Layer, renders a Jinja2 HTML template with the session data, writes the output to a temp file, and opens it in the user's default browser.

**Responsibilities:**
- Query `daily_summaries` and `sessions` for the requested date
- Query `daily_summaries` for the past 7 days for the weekly trend section
- Render `templates/digest.html.j2` with the queried data
- Write the rendered HTML to `{user_app_data}/focusguard/reports/digest_{date}.html`
- Open the file using `webbrowser.open()`

**Template data contract:**
```python
{
    "date": "2024-11-15",
    "confirmed_count": 4,
    "confirmed_duration_mins": 47,
    "unconfirmed_count": 6,
    "sessions": [...],              # list of SessionRecord dicts
    "hourly_buckets": [...],        # 24-element list of confirmed minutes per hour
    "top_sites": [...],             # list of {site, duration_mins}
    "weekly_trend": [...]           # 7-element list of {date, confirmed_duration_mins}
}
```

**Chart.js** is bundled as a static file at `assets/chart.min.js` and referenced with a relative path in the template. The report works fully offline.

---

### 9. Settings UI

**Technology:** `Tkinter` (stdlib)
**Thread:** Must run on the main thread (Tkinter requirement on macOS); opened via `threading` callback from system tray
**Communication:** Reads and writes `config.json`; does not communicate with other components directly at runtime

The Settings UI is a Tkinter window opened on demand from the system tray. It reads the current `config.json` on open and writes back on save. All running components re-read config on their next cycle (polling-based config refresh, no hot-reload signals needed given the low frequency of settings changes).

**Configurable fields:**

| Field | Type | Default |
|---|---|---|
| Distracting sites/apps list | Editable list | Built-in defaults |
| Idle threshold | Integer (seconds) | 30 |
| Confirmation window | Integer (seconds) | 120 |
| Gaze detection FPS | Integer | 5 |
| Webcam device index | Integer | 0 |
| End-of-day digest time | HH:MM string | 17:30 |
| Launch at startup | Boolean | true |
| Webcam toggle default | Boolean (ON at start) | true |

---

## Inter-Component Communication Summary

| From | To | Method | Data |
|---|---|---|---|
| Activity Monitor | Session Manager | Direct method call | `window_signal`, `site_or_app` |
| Browser Extension | Flask server | HTTP POST to `127.0.0.1:5678/url` | `{ url, browser }` |
| Flask server | Activity Monitor | Shared thread-safe variable | URL string |
| Idle Detector | Session Manager | Direct method call | `idle_signal` |
| Gaze Detector | Session Manager | Direct method call | `gaze_signal` |
| Gaze Detector | System Tray Controller | Direct method call | Error / clear error |
| Session Manager | Database Layer | Direct method call | `SessionRecord` |
| Report Generator | Database Layer | Direct method call | Query results |
| Settings UI | Config file | File I/O (`config.json`) | Full config dict |
| System Tray Controller | All components | Direct method calls | Start / stop / toggle signals |

---

## Data Flow: Confirmed Doomscroll Session (End-to-End)

```
1. USER OPENS REDDIT IN BROWSER
   │
   ├─► Browser extension detects tab URL change
   │   └─► POST http://127.0.0.1:5678/url  { "url": "https://reddit.com/..." }
   │       └─► Flask handler writes URL to shared variable
   │
   └─► Activity Monitor polls (next 2s tick)
       └─► Reads URL from shared variable → matches "reddit.com" in distracting list
           └─► session_manager.on_window_signal(state="DISTRACTING", site="reddit.com")
               └─► Session Manager: window_signal = DISTRACTING ✓

2. USER STOPS TYPING (hands leave keyboard/mouse)
   │
   └─► pynput detects no input events
       └─► Idle Detector: elapsed > 30s threshold
           └─► session_manager.on_idle_signal(state="IDLE")
               └─► Session Manager: idle_signal = IDLE ✓

3. GAZE DETECTOR CONFIRMS EYES ON SCREEN
   │
   └─► OpenCV captures frame → MediaPipe Face Mesh runs
       └─► EAR + iris offset → classified as LOOKING
           └─► session_manager.on_gaze_signal(state="LOOKING")
               └─► Session Manager: gaze_signal = LOOKING ✓

4. THREE-SIGNAL ALIGNMENT — SESSION OPENS
   │
   └─► Session Manager evaluates: DISTRACTING + IDLE + LOOKING = confirmed_condition TRUE
       └─► active_session = new SessionRecord(start=now, site="reddit.com")

5. SIGNALS REMAIN ALIGNED FOR 2+ MINUTES
   │
   └─► Session Manager: current_duration >= confirmation_window (120s)
       └─► Session remains open, duration tracked

6. USER MOVES MOUSE — IDLE SIGNAL BREAKS
   │
   └─► pynput detects mouse event
       └─► session_manager.on_idle_signal(state="ACTIVE")
           └─► Session Manager: idle_signal = ACTIVE → confirmed_condition FALSE
               └─► duration = 4m 32s >= 120s → classify as CONFIRMED
                   └─► database_layer.write_session(SessionRecord{
                           started_at:     "2024-11-15T14:22:00Z",
                           ended_at:       "2024-11-15T14:26:32Z",
                           duration_secs:  272,
                           site_or_app:    "reddit.com",
                           classification: "confirmed",
                           window_signal:  1,
                           idle_signal:    1,
                           gaze_signal:    1,
                           gaze_status:    "LOOKING"
                       })
                       └─► SQLite INSERT into sessions table ✓
                           └─► daily_summaries updated ✓

7. END OF DAY — REPORT GENERATED
   │
   └─► System Tray Controller triggers Report Generator at 17:30
       └─► db.get_sessions_for_date("2024-11-15") → returns all sessions
           └─► db.get_weekly_summaries(...) → returns 7-day trend
               └─► Jinja2 renders digest.html.j2 with session data + Chart.js
                   └─► HTML written to reports/digest_2024-11-15.html
                       └─► webbrowser.open(report_path) → opens in default browser ✓
```

---

## File Structure

```
focusguard/
├── main.py                         # Entry point — initializes and starts all components
├── config.json                     # User configuration (written by Settings UI)
│
├── core/
│   ├── session_manager.py          # Three-signal confirmation logic and session lifecycle
│   ├── database_layer.py           # SQLite read/write interface
│   └── event_types.py              # Signal state constants and SessionRecord dataclass
│
├── detectors/
│   ├── activity_monitor.py         # pygetwindow + psutil window polling
│   ├── idle_detector.py            # pynput keyboard/mouse idle tracking
│   └── gaze_detector.py            # OpenCV + MediaPipe gaze detection (core)
│
├── bridge/
│   ├── flask_server.py             # Local HTTP server for browser extension
│   └── url_state.py                # Thread-safe shared URL variable
│
├── ui/
│   ├── tray_controller.py          # pystray system tray icon and menu
│   └── settings_window.py          # Tkinter settings UI
│
├── reporting/
│   ├── report_generator.py         # Jinja2 report rendering and browser launch
│   └── templates/
│       └── digest.html.j2          # Daily digest HTML template
│
├── assets/
│   └── chart.min.js                # Bundled Chart.js (offline-capable)
│
├── extension/                      # Browser extension source
│   ├── manifest.json               # Manifest V3
│   ├── background.js               # Service worker — tab URL monitoring
│   └── icons/
│
└── tests/
    ├── test_session_manager.py
    ├── test_activity_monitor.py
    ├── test_idle_detector.py
    ├── test_gaze_detector.py
    └── test_report_generator.py
```

**User data directory** (outside the install directory, not bundled):
```
{user_app_data}/focusguard/
├── focusguard.db                   # SQLite database
├── focusguard.log                  # Internal error log
└── reports/
    ├── digest_2024-11-14.html
    └── digest_2024-11-15.html
```

- **Windows:** `%APPDATA%\focusguard\`
- **macOS:** `~/Library/Application Support/focusguard/`

---

## Configuration Management

All user-configurable settings are stored in a single `config.json` file in the user data directory. The Settings UI is the only component that writes to this file. All other components read it at startup and re-read it on their next poll cycle after a change is saved.

**config.json schema:**
```json
{
  "distracting_sites": ["reddit.com", "twitter.com", "news.ycombinator.com"],
  "distracting_apps":  ["Slack", "Discord"],
  "idle_threshold_secs": 30,
  "confirmation_window_secs": 120,
  "gaze_fps": 5,
  "gaze_retry_interval_secs": 30,
  "webcam_device_index": 0,
  "webcam_enabled_on_start": true,
  "flask_port": 5678,
  "end_of_day_time": "17:30",
  "launch_at_startup": true
}
```

**Config loading pattern:** Each component receives the config dict at instantiation. Long-running components (Activity Monitor, Gaze Detector) re-read the config file at the start of each poll cycle to pick up changes without requiring a restart. The Settings UI writes atomically (write to `.tmp` then rename) to prevent partial reads.

---

## Threading Model

| Thread | Component | Type | Blocking? |
|---|---|---|---|
| Main | System Tray Controller (pystray) | Main thread | Yes — pystray blocks |
| T1 | Activity Monitor | `threading.Thread` (daemon) | Polls with `time.sleep(2)` |
| T2 | Idle Detector | `pynput` listener threads (internal) | Event-driven |
| T3 | Gaze Detector | `threading.Thread` (daemon) | Capture loop with sleep |
| T4 | Browser Extension Bridge (Flask) | `threading.Thread` (daemon) | Blocking server loop |
| On-demand | Report Generator | Called inline from tray callback | Fast; no dedicated thread |
| On-demand | Settings UI | Must run on main thread (macOS) | Modal window loop |

All detector threads are daemon threads — they are automatically terminated when the main thread exits. The Session Manager is not a thread; it is called synchronously from detector threads and holds a lock for under 1ms per call.
