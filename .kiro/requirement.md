# FocusGuard — Requirements

## Conventions

- **MUST** — mandatory requirement. The system will not be considered correct without it.
- **MUST NOT** — absolute prohibition.
- **SHOULD** — strongly recommended. Deviation requires documented justification.
- **MAY** — optional enhancement.

---

## 1. Activity Monitoring

### 1.1 Window & Process Tracking

**FR-1.1.1** The app MUST continuously monitor the active foreground window title and process name while running.

**FR-1.1.2** The app MUST poll the active window at a configurable interval (default: 1 second).

**FR-1.1.3** The app MUST extract the process executable name from the active window to identify the owning application.

**FR-1.1.4** The app SHOULD fall back to window title parsing for browser identification when the browser extension is unavailable.

### 1.2 Browser URL Tracking

**FR-1.2.1** The app MUST expose a local HTTP endpoint (bound to `127.0.0.1` only) that accepts URL updates from the companion browser extension.

**FR-1.2.2** The endpoint MUST accept `POST` requests containing the active tab URL and browser identifier.

**FR-1.2.3** The app MUST treat the browser extension URL as the authoritative source for browser activity, superseding window title heuristics when available.

**FR-1.2.4** The app MUST NOT bind the local HTTP server to any interface other than `127.0.0.1`.

**FR-1.2.5** The local HTTP server MUST be configurable on a user-defined port (default: a fixed localhost port defined in config).

### 1.3 Distracting Sites & Apps List

**FR-1.3.1** The app MUST maintain a configurable list of distracting domains and application names used to evaluate the window/URL signal.

**FR-1.3.2** The app MUST ship with a default list of commonly distracting domains (e.g., reddit.com, twitter.com, news sites) and applications.

**FR-1.3.3** The user MUST be able to add, remove, and edit entries in the distracting sites/apps list via the settings UI.

**FR-1.3.4** The app MUST persist the distracting sites/apps list across restarts.

**FR-1.3.5** Domain matching MUST be case-insensitive and MUST match subdomains (e.g., a rule for `reddit.com` MUST match `www.reddit.com` and `old.reddit.com`).

---

## 2. Idle Detection

### 2.1 Input Monitoring

**FR-2.1.1** The app MUST monitor keyboard and mouse input events to determine whether the user is actively interacting with their computer.

**FR-2.1.2** The app MUST track the elapsed time since the last keyboard or mouse event.

**FR-2.1.3** The idle signal MUST be set to active when no keyboard or mouse input has been detected for a duration equal to or exceeding the configured idle threshold.

**FR-2.1.4** The idle signal MUST be reset to inactive immediately upon any keyboard or mouse event.

### 2.2 Idle Threshold Configuration

**FR-2.2.1** The app MUST define a configurable idle threshold with a default value of 30 seconds.

**FR-2.2.2** The user MUST be able to adjust the idle threshold via the settings UI.

**FR-2.2.3** The idle threshold MUST accept integer values in seconds, with a minimum of 10 seconds and a maximum of 300 seconds.

---

## 3. Gaze Detection

> Webcam-based gaze detection is a **required core component** of the confirmed doomscroll detection pipeline. It is not an optional add-on. The system cannot produce confirmed doomscroll logs without it.

### 3.1 Detection Pipeline

**FR-3.1.1** The app MUST include webcam-based gaze detection using OpenCV for frame capture and MediaPipe Face Mesh for facial landmark analysis.

**FR-3.1.2** The gaze detection component MUST produce a binary output per detection window: `LOOKING` (user's gaze is directed at the screen) or `NOT_LOOKING`.

**FR-3.1.3** The gaze detection component MUST run on-device using the local CPU. No cloud inference or external API calls are permitted.

**FR-3.1.4** The gaze detection loop MUST operate at a configurable frame rate (default: 5 FPS) to limit CPU usage while maintaining responsive detection.

**FR-3.1.5** The app MUST pass only the binary gaze result to the Session Manager. Raw frames, landmark coordinates, and intermediate model outputs MUST NOT be passed to any other component or persisted in any form.

### 3.2 Webcam Toggle

**FR-3.2.1** The app MUST provide a manual ON/OFF toggle for the webcam gaze detection component, accessible from the system tray menu.

**FR-3.2.2** When the toggle is set to OFF, the gaze detection loop MUST stop and the webcam MUST be released.

**FR-3.2.3** When the toggle is set to ON, the gaze detection loop MUST resume and the webcam MUST be re-acquired.

**FR-3.2.4** The webcam toggle state MUST be persisted across app restarts.

**FR-3.2.5** The system tray icon or menu MUST clearly indicate the current gaze detection state (ON / OFF) at all times.

**FR-3.2.6** When gaze detection is OFF, the app MUST NOT produce confirmed doomscroll session logs. Partial (unconfirmed) sessions MAY still be logged based on the remaining two signals.

### 3.3 Webcam Unavailability

**FR-3.3.1** If the webcam cannot be acquired at startup or during a session (device unavailable, permission denied, or in use by another application), the app MUST display a visible error indicator in the system tray.

**FR-3.3.2** The system tray error indicator MUST include a prompt or tooltip directing the user to resolve the webcam issue.

**FR-3.3.3** The app MUST continue running when the webcam is unavailable — it MUST NOT crash or exit.

**FR-3.3.4** While the webcam is unavailable, the app MUST NOT produce confirmed doomscroll session logs.

**FR-3.3.5** The app MUST automatically attempt to re-acquire the webcam at a configurable retry interval (default: 30 seconds) after a failure.

**FR-3.3.6** Once the webcam is successfully re-acquired, the app MUST resume normal gaze detection and clear the error indicator.

### 3.4 Privacy — Webcam Data

**FR-3.4.1** The app MUST NOT write any webcam frames, video segments, or image files to disk at any time.

**FR-3.4.2** The app MUST NOT transmit any webcam data over any network interface.

**FR-3.4.3** The app MUST NOT retain raw frame data in memory beyond the processing of a single frame.

---

## 4. Session Detection & Logging

### 4.1 Three-Signal Confirmation Model

**FR-4.1.1** The app MUST evaluate three signals continuously: the window/URL signal, the idle signal, and the gaze signal.

**FR-4.1.2** A session MUST be classified as **confirmed** only when all three signals are simultaneously active for a sustained duration equal to or exceeding the confirmation window (default: 2 minutes).

**FR-4.1.3** A session MUST be classified as **unconfirmed** when one or two signals are active but the full three-signal alignment is not met.

**FR-4.1.4** The confirmation window duration MUST be configurable by the user (minimum: 30 seconds, maximum: 10 minutes).

**FR-4.1.5** Signal state transitions MUST be evaluated at the same interval as the window polling rate (default: 1 second).

### 4.2 Session Records

**FR-4.2.1** The app MUST log every detected session (confirmed and unconfirmed) to the local SQLite database.

**FR-4.2.2** Each session record MUST include:
- Start timestamp (UTC)
- End timestamp (UTC)
- Duration in seconds
- Site domain or application name
- Classification: `confirmed` or `unconfirmed`
- Signals triggered: a record of which of the three signals were active during the session
- Gaze status at time of logging: `LOOKING`, `NOT_LOOKING`, or `UNAVAILABLE`

**FR-4.2.3** The app MUST NOT modify or delete session records after they are written. Session history is append-only.

**FR-4.2.4** The app SHOULD write session records atomically to prevent partial writes on unexpected shutdown.

---

## 5. Dashboard & Reporting

### 5.1 Daily Digest

**FR-5.1.1** The app MUST generate a Daily Digest HTML report on demand and at a user-configured end-of-day time (default: 5:30 PM).

**FR-5.1.2** The Daily Digest MUST be a self-contained HTML file that opens in the user's default browser without requiring an internet connection.

**FR-5.1.3** The Daily Digest MUST include:
- Total number of confirmed doomscroll sessions for the day
- Total confirmed doomscroll duration (in minutes)
- Total number of unconfirmed sessions
- A timeline or heatmap showing session distribution by hour of day
- A ranked list of top distracting sites and applications by time spent

**FR-5.1.4** The Daily Digest SHOULD include a weekly trend comparison showing confirmed doomscroll time across the past 7 days.

**FR-5.1.5** The user MUST be able to navigate to previous days' digests from within the report.

**FR-5.1.6** The app MUST notify the user via a system tray notification when the end-of-day digest is ready.

**FR-5.1.7** The digest notification MUST be non-intrusive — it MUST NOT use modal dialogs, audio alerts, or full-screen overlays.

### 5.2 Report Generation

**FR-5.2.1** The HTML report MUST be generated using Jinja2 templates populated with data queried from the local SQLite database.

**FR-5.2.2** Charts and visualizations MUST be rendered using Chart.js, bundled locally with the application (not loaded from a CDN).

**FR-5.2.3** The app MAY allow the user to export session data as CSV for use in external tools.

---

## 6. Privacy & Data Handling

**FR-6.1** The app MUST operate entirely offline. The only permitted network activity is communication between the browser extension and the local HTTP server on `127.0.0.1`.

**FR-6.2** The app MUST NOT make any outbound network requests to external hosts.

**FR-6.3** The app MUST NOT transmit any user data, session logs, or behavioral signals to any external server or service.

**FR-6.4** The app MUST NEVER store webcam frames, video, or image data in any form (memory beyond single-frame processing, disk, or network).

**FR-6.5** All user data — session logs, configuration, and generated reports — MUST be stored locally on the user's machine only.

**FR-6.6** The app SHOULD store all local data in a clearly documented, user-accessible directory so users can inspect, back up, or delete their data at any time.

---

## 7. System Tray & UI

**FR-7.1** The app MUST run as a system tray application with no persistent main window during normal operation.

**FR-7.2** The system tray menu MUST provide access to: gaze detection toggle, settings, open today's digest, and quit.

**FR-7.3** The app MUST launch at system startup by default, with an option to disable auto-start in settings.

**FR-7.4** The settings UI MUST be accessible from the system tray and MUST allow configuration of: idle threshold, confirmation window duration, distracting sites/apps list, digest notification time, and webcam device selection.

**FR-7.5** The app MUST NEVER display modal dialogs, pop-ups, or interruptions during an active work session.

---

## 8. Non-Functional Requirements

### 8.1 Performance

**NFR-8.1.1** The app MUST consume no more than 5% average CPU on a modern dual-core machine during normal background operation (excluding gaze detection processing).

**NFR-8.1.2** The gaze detection loop MUST consume no more than 15% average CPU on a modern dual-core machine when running at the default 5 FPS.

**NFR-8.1.3** The app MUST consume no more than 300 MB of RAM during normal operation with gaze detection active.

**NFR-8.1.4** The app MUST start and reach a fully operational state (all monitors active) within 10 seconds of launch on a standard machine.

**NFR-8.1.5** Daily Digest HTML report generation MUST complete within 3 seconds for up to 1 year of stored session data.

### 8.2 Privacy & Security

**NFR-8.2.1** The local HTTP server MUST only accept connections from `127.0.0.1`. Connections from any other address MUST be rejected.

**NFR-8.2.2** The local SQLite database MUST be stored in the user's application data directory with file permissions restricted to the current user.

**NFR-8.2.3** The app MUST NOT log, cache, or persist any data beyond what is explicitly defined in the session record schema (FR-4.2.2).

### 8.3 Reliability

**NFR-8.3.1** The app MUST run continuously in the background without crashing for a minimum of 8 hours under normal operating conditions.

**NFR-8.3.2** The app MUST recover gracefully from transient errors in any individual signal source (window tracking failure, browser extension disconnect, webcam loss) without terminating.

**NFR-8.3.3** The app MUST log internal errors to a local log file for debugging without surfacing them to the user unless action is required.

**NFR-8.3.4** On unexpected shutdown, the app MUST NOT leave partial or corrupt session records in the database.

### 8.4 Usability

**NFR-8.4.1** The app MUST NOT interrupt, block, or visually distract the user during any active work session.

**NFR-8.4.2** All user-facing notifications MUST be limited to the system tray — no modal dialogs, audio alerts, or screen overlays.

**NFR-8.4.3** First-time setup MUST be completable in under 5 minutes, including permission grants and browser extension installation.

**NFR-8.4.4** The settings UI MUST clearly explain the purpose of each configurable option.

**NFR-8.4.5** The app SHOULD provide a brief onboarding flow on first launch explaining the three-signal detection model and the privacy guarantees.

### 8.5 Portability

**NFR-8.5.1** The app MUST run on Windows 10 or later (64-bit).

**NFR-8.5.2** The app MUST run on macOS 12 (Monterey) or later.

**NFR-8.5.3** The app MUST be distributable as a standalone installer that does not require Python to be pre-installed on the user's machine.

**NFR-8.5.4** The packaged installer MUST NOT require administrator/root privileges to install or run.

**NFR-8.5.5** The companion browser extension MUST support Chrome and Edge (Manifest V3). Firefox support (MV2/MV3) is SHOULD.

---

## 9. Constraints

**C-1** The application MUST be implemented in Python 3.10 or later.

**C-2** Gaze detection MUST use OpenCV and MediaPipe Face Mesh. Substituting these libraries requires explicit re-evaluation of this requirements document.

**C-3** All session data MUST be stored in SQLite using Python's built-in `sqlite3` module.

**C-4** The application MUST be packaged using PyInstaller for distribution.

**C-5** The application MUST NOT require a GPU. All ML inference MUST run on CPU.
