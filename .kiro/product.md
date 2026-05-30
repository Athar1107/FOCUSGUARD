# FocusGuard — Product Document

## Vision

FocusGuard is a silent, always-on productivity companion for knowledge workers. It uses AI to detect when you've drifted into passive doomscrolling — and instead of interrupting you, it simply remembers. At the end of the day, it shows you the truth about where your time went, so you can make better choices tomorrow.

No nudges. No pop-ups. No shame in the moment. Just honest data, delivered when you're ready to see it.

---

## Goals

1. **Accurate, low-false-positive detection** — Only log a session as a confirmed doomscroll when all three signals align: a distracting site is open, the user is visually engaged with the screen, and their hands are idle. Partial signal matches are recorded but not surfaced as confirmed.

2. **Zero interruption during work** — FocusGuard never breaks the user's flow. It observes passively and defers all feedback to the end-of-day review.

3. **Full local privacy** — All processing happens on-device. The webcam feed is never stored. No data is transmitted to any server. The only output from gaze detection is a binary signal (looking / not looking) per session window.

4. **Actionable end-of-day insight** — The daily digest gives users a clear, honest picture of their distraction patterns: confirmed sessions, near-misses, time-of-day heatmaps, and weekly trends.

5. **Low friction setup and operation** — The app lives in the system tray, starts on login, and requires minimal configuration. The webcam toggle is the primary user control during a work session.

---

## Non-Goals

- **No real-time interventions** — FocusGuard will not block sites, send alerts, or interrupt the user in any way during a session.
- **No cloud sync or accounts** — There is no backend, no user account, and no remote storage. All data stays on the local machine.
- **No webcam footage storage** — The raw video feed is never written to disk. Only the derived gaze signal is retained.
- **No content filtering or parental controls** — FocusGuard is not a content blocker. It detects behavioral patterns, not specific content.
- **No mobile support** — The initial product targets desktop (Windows and macOS) only.
- **No team or organizational features** — FocusGuard is a personal tool. There is no manager dashboard, reporting export, or multi-user mode.
- **No prescriptive productivity advice** — The app surfaces data; it does not tell users what to do with it.

---

## User Personas

### 1. The Remote Worker — "Maya"
- **Profile:** 32-year-old UX designer, fully remote, works from home 5 days a week
- **Pain point:** Opens Twitter "for a second" between tasks and loses 45 minutes without realizing it. Doesn't notice it happening in the moment.
- **Goal:** Understand her actual distraction patterns so she can protect her deep work hours
- **Relationship with tech:** Comfortable with desktop apps, privacy-conscious, dislikes notification spam

### 2. The Freelancer — "Carlos"
- **Profile:** 27-year-old freelance developer, works irregular hours, bills by the hour
- **Pain point:** Doomscrolling bleeds into billable time. He suspects it's worse than he thinks but has no data.
- **Goal:** Honest accounting of where his time goes, without a tool that makes him feel surveilled
- **Relationship with tech:** Power user, wants control over what's tracked, values local-first software

### 3. The Student — "Priya"
- **Profile:** 22-year-old graduate student, writes her thesis at home on a laptop
- **Pain point:** News and Reddit are her procrastination defaults. She opens them reflexively when stuck on a paragraph.
- **Goal:** Build awareness of her avoidance patterns to break the habit over time
- **Relationship with tech:** Moderate technical comfort, motivated by self-improvement, budget-conscious

---

## Core User Journey

### Setup (One-time)
1. User downloads and installs FocusGuard on their desktop.
2. On first launch, a brief onboarding flow explains the three detection signals and the privacy model (local-only, no video storage).
3. User grants necessary permissions: screen/window access, webcam access.
4. User optionally configures their list of distracting sites/apps (a default list is provided).
5. FocusGuard starts silently and adds itself to the system tray.

### During a Work Session (Passive)
1. FocusGuard runs in the background. No UI is visible unless the user opens the tray icon.
2. The app continuously evaluates three signals:
   - **Window/URL signal:** Is a distracting site or app in the foreground?
   - **Idle signal:** Have keyboard and mouse been inactive for a threshold period?
   - **Gaze signal:** Is the webcam detecting that the user is looking at the screen?
3. When all three signals align for a sustained period, the session is marked as a **confirmed doomscroll** and logged with a timestamp and duration.
4. Sessions where only one or two signals align are logged as **unconfirmed** (partial matches) for context.
5. The user can toggle the webcam gaze detection ON/OFF from the system tray at any time. When OFF, gaze is treated as unknown and confirmed doomscrolls cannot be logged.

### End of Day (Review)
1. At a user-configured time (default: 5:30 PM), a subtle tray notification invites the user to review their day.
2. The user opens the **Daily Digest** dashboard.
3. The dashboard shows:
   - Total confirmed doomscroll time for the day
   - A timeline view of when sessions occurred
   - Breakdown of confirmed vs. unconfirmed sessions
   - Top distracting sites/apps
   - A heatmap of distraction by hour of day
4. The user can navigate to previous days and view **weekly trend charts** showing whether their patterns are improving over time.
5. No action is required — the user closes the dashboard and continues their evening.

---

## Detection Model: The Three-Signal Rule

A session is logged as a **confirmed doomscroll** only when all three conditions are simultaneously true for a sustained window (default: 2 minutes):

| Signal | Source | Confirmed State |
|---|---|---|
| Window/URL | OS window manager + browser extension or accessibility API | Distracting site/app is in the foreground |
| Idle detection | Keyboard & mouse event monitoring | No keyboard or mouse input for threshold period |
| Gaze detection | Webcam + on-device ML model | User is looking at the screen |

**Partial matches** (1 or 2 signals active) are recorded as unconfirmed sessions and shown in the digest for context, but are not counted toward the confirmed doomscroll total.

The webcam gaze detection is a core, required component of the detection pipeline. It is the signal that distinguishes passive staring (doomscrolling) from stepping away from the desk (idle but not scrolling).

---

## Success Metrics

### Adoption & Retention
- **D7 retention:** ≥ 60% of users who install FocusGuard open the Daily Digest at least once in their first week
- **D30 retention:** ≥ 40% of users are still running FocusGuard with gaze detection enabled after 30 days

### Detection Quality
- **Confirmed doomscroll precision:** User-reported false positive rate < 10% (surveyed via optional in-app feedback)
- **Gaze detection uptime:** Webcam gaze signal is active for ≥ 80% of logged work session time (when toggled ON)

### User Value
- **Digest engagement:** ≥ 70% of active users open the Daily Digest at least 3 times per week
- **Perceived accuracy:** ≥ 75% of users who provide feedback rate their confirmed doomscroll log as "accurate" or "mostly accurate"

### Privacy & Trust
- **Zero data egress:** No telemetry, no network calls to external servers (verifiable via open-source release or network audit)
- **Webcam footage:** Zero bytes of raw video written to disk at any time

---

## Platform & Technical Constraints

- **Languages/Runtime:** Python-based desktop application
- **Platforms:** Windows 10+ and macOS 12+
- **Distribution:** Standalone installer (no app store dependency for initial release)
- **System tray:** Primary UI surface during work sessions
- **On-device ML:** Gaze detection model runs locally (e.g., MediaPipe or equivalent); no GPU required for baseline accuracy
- **Browser URL tracking:** Via browser extension or OS accessibility APIs (platform-dependent)
- **Data storage:** Local SQLite database; all session logs stored on-device only
