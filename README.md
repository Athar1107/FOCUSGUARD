# 🛡️ FocusGuard

FocusGuard is a premium, real-time focus tracking and doomscroll detection application. It monitors active window signals, idle inputs, and user gaze (via webcam) to log distracting sessions and generate timezone-aware daily HTML digests.

---

## 🚀 How FocusGuard Works

FocusGuard uses a three-signal state machine to determine when you are doomscrolling:
1. **Window Signal**: Detects if your active window matches a distracting website/app (e.g., YouTube, Instagram, Reddit).
2. **Idle Signal**: Tracks keyboard/mouse inputs using global hooks to determine if you are active or inactive.
3. **Gaze Signal**: Analyzes your webcam feed in real-time using OpenCV and MediaPipe Face Mesh to verify if you are looking at the screen.

### 📊 Doomscroll Tiers
* **Tier 2 (Confirmed)**: Distracting window open + User is idle + User is looking at the screen.
* **Tier 1 (Unconfirmed)**: Distracting window open + User is idle + Gaze is not looking/camera unavailable.

---

## 🛠️ Configuration (`data/config.json`)

You can customize FocusGuard's behavior by editing the `data/config.json` file:
* `idle_threshold_seconds`: The duration of keyboard/mouse inactivity required to be marked as **Idle** (e.g., `2` seconds for fast testing, `30` seconds default).
* `min_session_duration_seconds`: The minimum duration of a distracting session to be saved in the database (e.g., `2` seconds for testing).
* `distracting_sites`: List of website domains to track as distraction candidates.
* `webcam_enabled`: Toggle gaze tracking using the webcam (`true`/`false`).
* `gaze_ear_closed_threshold`: EAR cutoff below which the detector treats the eyes as closed; higher values make the detector less tolerant of partially closed eyes.
* `gaze_iris_offset_threshold`: Iris offset cutoff above which the detector treats the eyes as looking away; lower values make sideways gaze detection stricter.
* `gaze_stable_frames`: Number of consecutive frames a gaze state must hold before the app emits a state change; higher values reduce flicker.
* `cognitive_load`: Nested Phase 3B settings for milestone timing and message weighting.

  ```json
  "cognitive_load": {
    "milestones_minutes": [90, 180, 240, 300],
    "time_of_day_weights": {
      "morning": { "calm": 4, "analytical": 4, "energetic": 1, "encouraging": 1 },
      "afternoon": { "calm": 1, "analytical": 1, "energetic": 4, "encouraging": 4 },
      "evening": { "calm": 5, "analytical": 2, "energetic": 1, "encouraging": 2 }
    }
  }
  ```

---

## 🧪 Testing Your First Session (Real-Time)

To verify the app is logging sessions successfully in real-time, try the **YouTube Video Test**:

1. Start FocusGuard in your terminal:
   ```bash
   python main.py
   ```
2. Open Chrome/Edge and go to **`youtube.com`**.
3. Play any video.
4. **Sit back and watch the video for at least 15–20 seconds without touching your mouse or keyboard.**
   * *Because your hands are off, the idle detector will transition to `IDLE` after the configured threshold.*
   * *Gaze tracking will detect you looking at the screen, opening a Tier 2 Confirmed session.*
5. **Move your mouse** to end the session.
6. Right-click the circular FocusGuard icon in your system tray and select **Open Today's Digest**.
7. Refresh your browser to see your logged distraction session!

---

## 📂 Project Architecture

* `core/`
  * [database_layer.py](file:///c:/Users/athar/coding/focusgaurd/core/database_layer.py): SQLite interaction, schema setup, local timezone conversion.
  * [session_manager.py](file:///c:/Users/athar/coding/focusgaurd/core/session_manager.py): Three-signal confirmation machine.
  * [event_types.py](file:///c:/Users/athar/coding/focusgaurd/core/event_types.py): State definitions and SessionRecord dataclass.
* `detectors/`
  * [activity_monitor.py](file:///c:/Users/athar/coding/focusgaurd/detectors/activity_monitor.py): Active window polling (extension integration + title keyword fallbacks).
  * [idle_detector.py](file:///c:/Users/athar/coding/focusgaurd/detectors/idle_detector.py): Keyboard and mouse event listeners via `pynput`.
  * [gaze_detector.py](file:///c:/Users/athar/coding/focusgaurd/detectors/gaze_detector.py): OpenCV and MediaPipe-based gaze tracking.
* `reporting/`
  * [report_generator.py](file:///c:/Users/athar/coding/focusgaurd/reporting/report_generator.py): Jinja2 HTML report generator with offline Chart.js integration.
* `bridge/`
  * Flask API server receiving browser extensions URLs.
* [main.py](file:///c:/Users/athar/coding/focusgaurd/main.py): Application entry point and tray UI controller.

---

## 📈 Recent Improvements
* **Cognitive Load Awareness**: Added weighted motivational reminders for sustained focus at 90, 180, 240, and 300+ minutes.
* **Timezone Bug Fixes**: Corrected timezone offsets for session storage and aggregate weekly reporting.
* **Fallback Title Heuristics**: Added enhanced page-title keyword heuristics to detect distracting sites even when the browser extension is not installed.
* **Pathing & URIs**: Resolved absolute file path errors on Windows when loading reports in Chrome.
* **Windows Console Encoding**: Fixed crash issues on Windows console terminals by removing special unicode characters.
