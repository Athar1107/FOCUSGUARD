# FocusGuard — Phase Plan

## Phase 1 — Core Detection and Tray (Complete)

- Full project folder structure
- SQLite database with complete schema (sessions, sites, config, daily_summaries)
- Config system (config.json, defaults, atomic writes)
- Activity Monitor — polls active window every 2s, matches against distracting sites list
- Idle Detector — pynput keyboard/mouse listener, 7s threshold (configurable)
- Browser Extension Bridge — Flask server on 127.0.0.1:5678
- System tray (pystray) — webcam toggle, open digest, quit
- Tier 1 (unconfirmed) session logging to SQLite

---

## Phase 2 — Gaze Detection and Daily Digest (Complete)

- Gaze Detector — OpenCV + MediaPipe FaceLandmarker (Tasks API)
  - Captures webcam at 5 FPS
  - Eye Aspect Ratio (EAR) + iris offset for LOOKING / NOT_LOOKING classification
  - Emits binary gaze signal to Session Manager every 3 seconds
  - Handles webcam unavailability — retry every 30s, red tray icon on error
  - Zero frame storage — frames discarded immediately after processing
  - Model auto-downloaded on first run, cached in data/models/
- Tier 2 (confirmed) session logging — all three signals aligned
- Full Daily Digest HTML report (digest.html.j2)
  - Dark mode dashboard
  - Stat cards: confirmed sessions, unconfirmed sessions, total distraction time
  - Hourly heatmap bar chart (Chart.js)
  - 7-day weekly trend line chart (Chart.js)
  - Top distracting sites with progress bars
  - Session log table with tier and gaze status badges
  - Fully offline — Chart.js bundled locally, no CDN

---

## Phase 3 — Real-time Awareness Alerts (In Progress)

### 3a — Focused Work Reminder
- Alert after 3+ hours of continuous active work
  - Non-modal popup notification
  - Auto-closes after 5 minutes
  - Message: awareness of extended focus, suggestion to take a break
- Alert after 3+ hours of idle time
  - Popup requires user click to dismiss
  - Resumes FocusGuard monitoring after dismissal

### 3b — Cognitive Load Awareness with Random Motivational Messages (Complete)
- Triggers at 90, 180, 240, and 300+ minutes of continuous focus
- Milestone timings and time-of-day weighting are editable through the nested `cognitive_load` config section
- Each trigger selects a random message from a curated library
- Same message is never shown twice in a row
- Messages are motivational and supportive in tone — not guilt-based or prescriptive
- Message library covers four moods:
  - Energetic — direct, high-energy encouragement
  - Calm — measured, reassuring awareness
  - Analytical — data-grounded, rational framing
  - Encouraging — warm, affirming support
- Random selection is weighted by time of day:
  - Morning (before 12pm): Calm and Analytical weighted higher
  - Afternoon (12pm–5pm): Energetic and Encouraging weighted higher
  - Evening (after 5pm): Calm weighted higher
- Message examples (no emoji):
  - "3 hours of deep work. That is real. Take 15 minutes — you have earned it."
  - "You are in the zone. Just remember: your best ideas come after a reset."
  - "Your brain has been working hard. Feed it a break."
  - "Focus this sharp is rare. Protect it with a short rest."
  - "4 hours down. Step away for 20 — come back stronger."
  - "Sustained concentration is demanding. A short break now sharpens what comes next."
  - "You have been focused for a long time. The work will still be there after a walk."
  - "Deep work is valuable. So is knowing when to stop and recover."
- New module: core/work_reminder.py
- New module: core/cognitive_load.py

### 3c — Focus Health Report in Daily Digest
- Longest continuous focus session of the day
- Distribution of session lengths across the day (short, medium, extended)
- Average break duration between focus sessions
- Comparison to previous 7-day average

---

## Phase 4 — Auto Start and Settings UI (Planned)

### Auto Start
- Register FocusGuard to launch at OS startup
  - Windows: write to HKCU\Software\Microsoft\Windows\CurrentVersion\Run via winreg
  - macOS: create a launchd plist in ~/Library/LaunchAgents
- Toggle controlled from settings UI and persisted in config.json

### Settings UI (Tkinter)
- Accessible from system tray menu
- Configurable fields:
  - Distracting sites list (add, remove, enable/disable per entry)
  - Distracting apps list
  - Idle threshold (seconds)
  - Confirmation window duration (seconds)
  - Webcam device selection (dropdown from detected devices)
  - Gaze detection FPS
  - Work hours start and end time
  - End-of-day digest notification time
  - Auto-start on login toggle
- Writes config.json atomically on save
- All running components pick up changes on next poll cycle without restart

---

## Phase 5 — PyInstaller Packaging (Planned)

- Package entire app as standalone binary
  - Windows: single .exe installer, no Python required
  - macOS: .app bundle with notarization
- Bundle includes:
  - Python interpreter and all dependencies
  - MediaPipe FaceLandmarker model (data/models/)
  - Chart.js static asset
  - Jinja2 digest template
  - Default config.json
- PyInstaller flags required for this stack:
  - --collect-data mediapipe
  - --collect-models mediapipe
  - --collect-submodules cv2
- Code signing recommended for Windows to avoid antivirus false positives
- Expected bundle size: 150-300 MB
