# FocusGuard — Tools & Technology Reference

This document lists every tool, library, and framework used in FocusGuard, with justification for each choice, known limitations, and version pinning recommendations.

---

## Language

### Python 3.10+
**Purpose:** Core application language for all components — detection pipeline, data storage, dashboard generation, and UI.

**Why chosen:** Python has the richest ecosystem for the specific combination of capabilities FocusGuard needs: computer vision (OpenCV, MediaPipe), input monitoring (pynput), system integration (psutil, pygetwindow), and rapid UI prototyping. The alternatives (Rust, Go, C++) would require significantly more effort for the ML and CV components with no meaningful benefit for a single-user desktop tool.

**Why 3.10+ specifically:** Structural pattern matching (`match`/`case`) simplifies signal state logic. `3.10` is the oldest version still receiving security updates as of 2024 and is widely supported by all dependencies in this stack.

**Limitations:** Python's GIL means true parallelism requires multiprocessing rather than threading for CPU-bound tasks (relevant for the gaze detection loop). Startup time is slower than compiled languages, mitigated by PyInstaller bundling.

**Version pin:** `python >= 3.10, < 3.13` (3.13 introduces breaking changes in some C-extension dependencies; validate before upgrading)

---

## System Tray & UI

### pystray `~= 0.19`
**Purpose:** Creates and manages the system tray icon on both Windows and macOS. Hosts the gaze detection ON/OFF toggle, quick status display, and links to open the Daily Digest.

**Why chosen:** pystray is the de facto standard for cross-platform Python system tray apps. It abstracts over Win32 `Shell_NotifyIcon` on Windows and `NSStatusBar` on macOS with a single API. Alternatives like `infi.systray` are Windows-only; `rumps` is macOS-only.

**Limitations:** Menu rendering is native per platform, so complex custom UI inside the tray menu is not feasible — keep menu items simple and delegate richer UI to Tkinter or the HTML dashboard. Icon updates (e.g., showing gaze status) require calling `icon.update_menu()` which can flicker on some macOS versions.

**Version pin:** `pystray~=0.19.5`

---

### Tkinter (stdlib)
**Purpose:** Settings window — lets users configure their distracting sites list, idle threshold, digest notification time, and webcam device selection.

**Why chosen:** Tkinter ships with CPython on all platforms, meaning zero additional dependencies for a functional settings UI. For a settings panel that users open infrequently, the native-widget look is acceptable and the zero-install cost is a significant advantage. Alternatives like PyQt6 or wxPython would add 30–60 MB to the packaged binary and introduce licensing considerations (PyQt6 is GPL/commercial).

**Limitations:** Tkinter's styling is dated and not easily themed to match modern OS aesthetics. It is not suitable for the data-rich Daily Digest — that responsibility is delegated to the HTML dashboard. On macOS, Tkinter requires the system Python's Tcl/Tk or a separately installed version; PyInstaller handles this in the bundle.

**Version pin:** Bundled with Python stdlib — no separate pin needed. Validate against Python 3.10–3.12 during CI.

---

## Activity Tracking

### pygetwindow `~= 0.0.9`
**Purpose:** Retrieves the title and process name of the currently active (foreground) window. Used as the first signal in the three-signal detection pipeline to determine whether a distracting app is in focus.

**Why chosen:** pygetwindow provides a simple, cross-platform API for active window detection without requiring platform-specific Win32 or AppKit calls. For the subset of functionality FocusGuard needs (active window title + process name), it covers both Windows and macOS cleanly.

**Limitations:** On macOS, pygetwindow requires Accessibility permissions granted by the user. It does not provide the full URL of a browser tab — that gap is filled by the browser extension + Flask server. Window title parsing for browser windows (e.g., "Reddit — Chrome") is a fallback heuristic only; the browser extension is the authoritative URL source.

**Version pin:** `pygetwindow~=0.0.9` (project has been stable/unmaintained; pin to exact minor to avoid surprises)

---

### psutil `~= 5.9`
**Purpose:** Supplements pygetwindow with process-level information — process name, executable path, and CPU/memory stats. Used to reliably identify which application owns the foreground window, especially when window titles are ambiguous.

**Why chosen:** psutil is the standard cross-platform process and system utilities library for Python. It is actively maintained, well-tested, and used by major projects. No credible alternative exists for this use case.

**Limitations:** Some process metadata (e.g., full command line) requires elevated privileges on Windows. FocusGuard only needs process name and path, which are available without elevation.

**Version pin:** `psutil~=5.9.8`

---

## Browser URL Tracking

### Browser Extension (custom, lightweight)
**Purpose:** Captures the active tab's full URL in real time and POSTs it to the local Flask server. This is the authoritative source for browser URL data — window title parsing alone is too unreliable for accurate site classification.

**Why chosen:** There is no cross-browser Python API for reading active tab URLs without a browser extension. The extension approach is the standard pattern used by time-tracking tools (Wakatime, RescueTime, Toggl Track). A lightweight content script + background service worker is sufficient — no complex extension framework needed.

**Limitations:** Requires the user to install the extension in each browser they use. Extension must be updated if browser extension APIs change (Manifest V3 is the current standard for Chrome/Edge; Firefox supports both MV2 and MV3). The extension only captures URLs when the browser is the active window — this is intentional and consistent with the detection model.

**Implementation note:** The extension sends `POST /url` with `{ "url": "https://...", "browser": "chrome" }` to `http://localhost:{PORT}`. The port is configurable and stored in a local config file read by both the extension and the Flask server.

---

### Flask `~= 3.0`
**Purpose:** Minimal local HTTP server that receives URL updates from the browser extension. Runs as a background thread within the FocusGuard process.

**Why chosen:** Flask is the simplest way to stand up a local HTTP endpoint in Python. The server handles exactly one route (`POST /url`) and one route for health-checking (`GET /ping`). FastAPI would be overkill; the stdlib `http.server` module lacks the routing convenience. Flask's footprint in this role is minimal.

**Limitations:** Flask's development server is not production-grade, but for a localhost-only, single-connection use case (one browser extension posting to one local process) it is entirely appropriate. The server must bind to localhost only (`127.0.0.1`) — never `0.0.0.0` — to prevent exposure on the local network.

**Version pin:** `Flask~=3.0.3`

---

## Idle Detection

### pynput `~= 1.7`
**Purpose:** Monitors keyboard and mouse events to detect user idle state — the second signal in the three-signal detection pipeline. When no keyboard or mouse activity is detected for a configurable threshold (default: 60 seconds), the idle signal is set to active.

**Why chosen:** pynput is the standard cross-platform input monitoring library for Python. It supports both Windows and macOS with a unified API and runs listeners in background threads without blocking the main loop. Alternatives like `keyboard` and `mouse` are Windows-focused or require root on Linux.

**Limitations:** On macOS, pynput requires Accessibility permissions (same grant as pygetwindow — users see one permission prompt). Global keyboard listeners can conflict with some accessibility software. pynput captures input events but does not suppress them — FocusGuard is purely observational, so this is correct behavior.

**Version pin:** `pynput~=1.7.6`

---

## Gaze Detection (Core Feature)

### OpenCV (`opencv-python`) `~= 4.9`
**Purpose:** Captures frames from the webcam and preprocesses them (resize, color conversion) before passing to MediaPipe. Also handles webcam device enumeration for the settings UI.

**Why chosen:** OpenCV is the industry standard for computer vision in Python. Its `VideoCapture` API is the most reliable cross-platform webcam interface available. No alternative comes close in terms of stability, documentation, and community support.

**Limitations:** `opencv-python` bundles its own Qt libraries which can conflict with PyQt installations — since FocusGuard uses Tkinter, this is not an issue. The headless variant (`opencv-python-headless`) can be used instead to reduce binary size, since FocusGuard does not use OpenCV's GUI windows.

**Version pin:** `opencv-python-headless~=4.9.0.80` (prefer headless to avoid Qt bundling)

---

### MediaPipe `~= 0.10`
**Purpose:** Runs the Face Mesh model on webcam frames to detect facial landmarks. FocusGuard uses the eye landmark positions to determine whether the user's gaze is directed at the screen — the third and most critical signal in the detection pipeline.

**Why chosen:** MediaPipe Face Mesh is the best available option for on-device, real-time, CPU-only facial landmark detection in Python. It runs at 30+ FPS on a modern laptop CPU without a GPU, requires no model download at runtime (model is bundled), and provides 468 facial landmarks including precise eye region points sufficient for gaze estimation. Alternatives considered:

| Alternative | Reason not chosen |
|---|---|
| dlib + shape predictor | Slower, requires separate model file download, 68-point model is less precise for eyes |
| DeepFace | Overkill for binary gaze detection; heavier dependencies |
| GazeTracking (PyPI) | Thin wrapper around dlib; inherits dlib's limitations |
| Custom ONNX model | Requires model training/sourcing and ONNX Runtime dependency |

**Gaze detection approach:** Using the Eye Aspect Ratio (EAR) and iris landmark positions from Face Mesh, FocusGuard determines whether the user's eyes are open and oriented toward the screen. The output is a binary signal: `LOOKING` or `NOT_LOOKING`. No video frames or landmark coordinates are persisted — only this binary result per detection window.

**Limitations:** Accuracy degrades in low light, with glasses glare, or at extreme head angles. Detection requires the user's face to be visible to the webcam — this is expected and documented in onboarding. MediaPipe's Python API is marked as stable but Google has shifted focus to the Tasks API in 0.10+; migration path exists if needed.

**Version pin:** `mediapipe~=0.10.14`

---

## Local Database

### SQLite via `sqlite3` (stdlib)
**Purpose:** Stores all session logs locally — confirmed doomscroll sessions, unconfirmed partial matches, signal state snapshots, and user configuration. The entire data layer of FocusGuard.

**Why chosen:** SQLite is the correct choice for a single-user, local-only desktop application. It requires no server process, no configuration, and ships with Python's stdlib. The database is a single file the user can back up, inspect, or delete. For FocusGuard's write volume (a few dozen rows per day), SQLite has effectively unlimited headroom.

**Limitations:** SQLite does not support concurrent writes from multiple processes. FocusGuard is a single-process application (with threads), so this is not a concern. WAL mode (`PRAGMA journal_mode=WAL`) should be enabled to allow the Flask thread and the detection loop to read/write without blocking each other.

**Version pin:** Bundled with Python stdlib — no separate pin. Use `sqlite3.sqlite_version` at startup to log the SQLite version for debugging.

---

## Dashboard

### Jinja2 `~= 3.1`
**Purpose:** Templating engine for generating the Daily Digest HTML report. FocusGuard queries the SQLite database, passes the results to a Jinja2 template, and renders a self-contained HTML file that opens in the user's default browser.

**Why chosen:** Jinja2 is the standard Python templating library, already a dependency of Flask (so no additional install cost). It produces clean, readable HTML and supports the loops and conditionals needed to render session lists and summary statistics. Alternatives like Mako or string formatting are less ergonomic for HTML generation.

**Limitations:** The generated HTML is a static file — it does not auto-refresh. This is intentional: the digest is a point-in-time snapshot of the day. If the user wants to refresh, they re-open the digest from the tray menu.

**Version pin:** `Jinja2~=3.1.4` (already pinned transitively by Flask; explicit pin ensures consistency)

---

### Chart.js `3.x` (CDN or bundled)
**Purpose:** Renders the interactive charts in the Daily Digest HTML report — the hourly heatmap, session timeline, weekly trend line, and confirmed vs. unconfirmed breakdown bar chart.

**Why chosen:** Chart.js is the most widely used JavaScript charting library for straightforward data visualizations. It requires no build step, works as a single script tag, and produces clean, interactive charts out of the box. D3.js would offer more flexibility but requires significantly more code for standard chart types. Recharts and Victory require React.

**Bundling decision:** For a fully local, offline-capable app, Chart.js should be bundled with the PyInstaller package rather than loaded from CDN. This ensures the digest renders correctly without an internet connection.

**Limitations:** Chart.js is a client-side JS library — it has no Python integration. Data is passed from Jinja2 into the HTML template as inline JSON, which Chart.js reads on page load. This is a standard pattern and has no meaningful limitations for FocusGuard's data volumes.

**Version pin:** `3.4.x` (stable, well-documented; avoid 4.x until ecosystem catches up) — bundled as a static asset, not a Python dependency.

---

## Packaging & Distribution

### PyInstaller `~= 6.0`
**Purpose:** Packages the entire FocusGuard application — Python interpreter, all dependencies, MediaPipe models, Jinja2 templates, Chart.js assets, and the browser extension files — into a single standalone `.exe` (Windows) or `.app` (macOS). Users install FocusGuard without needing Python on their machine.

**Why chosen:** PyInstaller is the most mature and widely used Python packaging tool for desktop applications. It handles the complex dependency graphs of OpenCV and MediaPipe better than alternatives. `cx_Freeze` and `Nuitka` are viable alternatives but have less community support for the OpenCV/MediaPipe combination specifically.

**Limitations:** PyInstaller bundles are large (typically 150–300 MB for an OpenCV + MediaPipe app). Antivirus false positives are common for PyInstaller executables on Windows — code signing the `.exe` is strongly recommended for distribution. macOS `.app` bundles require notarization for Gatekeeper to allow execution without a warning.

**Known packaging considerations for this stack:**
- MediaPipe requires explicit `--collect-data mediapipe` and `--collect-models mediapipe` flags
- OpenCV headless requires `--collect-submodules cv2`
- pystray on macOS requires `rumps` to be excluded and `AppKit` to be included
- The browser extension files must be added via `--add-data`

**Version pin:** `pyinstaller~=6.6.0`

---

## Summary Table

| Tool | Version Pin | Role | Stdlib? |
|---|---|---|---|
| Python | `>=3.10,<3.13` | Language runtime | — |
| pystray | `~=0.19.5` | System tray icon & menu | No |
| Tkinter | stdlib | Settings UI | Yes |
| pygetwindow | `~=0.0.9` | Active window detection | No |
| psutil | `~=5.9.8` | Process identification | No |
| Browser extension | custom | Active browser URL capture | No |
| Flask | `~=3.0.3` | Local URL receiver server | No |
| pynput | `~=1.7.6` | Keyboard & mouse idle detection | No |
| opencv-python-headless | `~=4.9.0.80` | Webcam capture & frame processing | No |
| mediapipe | `~=0.10.14` | On-device gaze detection (Face Mesh) | No |
| sqlite3 | stdlib | Local session data storage | Yes |
| Jinja2 | `~=3.1.4` | HTML digest templating | No |
| Chart.js | `3.4.x` (bundled) | Dashboard charts & visualizations | No |
| PyInstaller | `~=6.6.0` | Standalone app packaging | No |

---

## Dependency File

The following is the recommended `requirements.txt` for development. PyInstaller is listed separately as a dev-only dependency.

```
# requirements.txt
pystray~=0.19.5
pygetwindow~=0.0.9
psutil~=5.9.8
Flask~=3.0.3
pynput~=1.7.6
opencv-python-headless~=4.9.0.80
mediapipe~=0.10.14
Jinja2~=3.1.4
```

```
# requirements-dev.txt
-r requirements.txt
pyinstaller~=6.6.0
```
