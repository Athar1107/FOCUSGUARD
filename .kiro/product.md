# FocusGuard — Product Document

## Vision

FocusGuard is a silent, always-on productivity companion for knowledge workers. It uses AI to detect when you've drifted into passive doomscrolling — and instead of interrupting you, it simply remembers. At the end of the day, it shows you the truth about where your time went, so you can make better choices tomorrow.

No nudges. No pop-ups. No shame in the moment. Just honest data, delivered when you're ready to see it.

---

## Goals

1. **Accurate, low-false-positive detection** — Only log a session as a confirmed doomscroll when all three signals align: a distracting site is open, the user is visually engaged with the screen, and their hands are idle. Partial signal matches are recorded but not surfaced as confirmed.

2. **Minimal, contextualized interruption** — FocusGuard prioritizes passive observation, but uses non-modal, dismissible, time-bounded alerts for awareness of unsustainable work patterns (extended focus sessions and prolonged idle periods). All feedback defers to end-of-day review when possible.

3. **Full local privacy** — All processing happens on-device. The webcam feed is never stored. No data is transmitted to any server. The only output from gaze detection is a binary signal (looking / not looking) per session window.

4. **Actionable end-of-day insight** — The daily digest gives users a clear, honest picture of their distraction patterns: confirmed sessions, near-misses, time-of-day heatmaps, and weekly trends.

5. **Low friction setup and operation** — The app lives in the system tray, starts on login, and requires minimal configuration. The webcam toggle is the primary user control during a work session.

---

## Non-Goals

- **No real-time interventions or control** — FocusGuard will not block sites, lock functionality, or enforce behavioral changes. Real-time alerts are awareness-focused only, never punitive or restrictive.
- **No cloud sync or accounts** — There is no backend, no user account, and no remote storage. All data stays on the local machine.
- **No webcam footage storage** — The raw video feed is never written to disk. Only the derived gaze signal is retained.
- **No content filtering or parental controls** — FocusGuard is not a content blocker. It detects behavioral patterns, not specific content.
- **No mobile support** — The initial product targets desktop (Windows and macOS) only.
- **No team or organizational features** — FocusGuard is a personal tool. There is no manager dashboard, reporting export, or multi-user mode.
- **No enforcement-based productivity advice** — The app surfaces data and offers research-backed awareness messages, but never prescribes actions or creates guilt-based messaging.

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

---

## Focused Work Reminder System

### Overview
FocusGuard includes a real-time work awareness system that notifies users when they've been continuously active for extended periods or idle for significant durations, helping them maintain sustainable work patterns through gentle reminders to rest and recover.

### Alert Behavior

#### Active Sessions (> 3 hours of continuous activity)
- **Trigger:** User has been actively working for more than 3 hours
- **Notification Type:** Popup alert
- **Display Duration:** Displays for 5 minutes
- **Auto-Close:** Alert automatically closes after 5 minutes
- **Purpose:** Reminds user to take a break after extended focus period
- **Alert Message:** "✅ You have been focused on the same task for 3 hours 12 minutes. Research suggests a 10–20 minute break can improve attention and decision quality."

#### Idle Sessions (≥ 3 hours of inactivity)
- **Trigger:** System remains idle for 3+ hours; alert appears after 15 minutes of idle time beyond the 3-hour threshold
- **Notification Type:** Popup alert
- **User Action Required:** User must click anywhere on the screen to dismiss the alert and restart FocusGuard's monitoring
- **Purpose:** Notifies user of extended inactivity and requires confirmation to resume operations

### Alert Summary

| Condition | Alert Timing | Alert Type | Dismissal Method | Auto-Close |
|-----------|-------------|-----------|-----------------|------------|
| Active session (>3 hrs) | After 3 hrs of activity | Popup | Auto-closes | Yes (5 min) |
| Idle session (≥3 hrs) | After 15 min beyond 3-hour idle threshold | Popup | Click anywhere | No |

### User Experience
- **Active Sessions:** Non-intrusive 5-minute popup reminder encouraging healthy breaks
- **Idle Sessions:** Requires user interaction to confirm awareness and restart monitoring
- Ensures users are aware of extended work sessions and idle periods
- Helps maintain healthy work patterns with explicit user confirmation during idle periods

---

## Cognitive Load Awareness System

### Overview
While the Focused Work Reminder System monitors active session duration and idle time, the Cognitive Load Awareness System tracks the quality and sustainability of focus during continuous work sessions. It detects prolonged focus periods and provides real-time awareness messages designed to help users understand their cognitive load, recognize potential fatigue patterns, and maintain sustainable productivity without guilt or pressure.

The system complements doomscroll detection by addressing a complementary user need: not just *where* time is spent, but also *how* the user is spending focused energy and whether focus intensity is sustainable.

### Design Philosophy
- **Awareness, not judgment** — Messages reflect patterns, not criticism
- **Sustainable productivity** — Encourage breaks and recovery based on research, not productivity maximization
- **Non-intrusive** — Notifications are gentle and easy to dismiss
- **Progress-oriented** — Celebrate focus and effort; acknowledge challenges
- **Personalization through diversity** — Dynamic message generation prevents repetition and feels natural

### Focus Session Categories

The system categorizes continuous focus sessions into four tiers based on duration:

| Category | Duration | Cognitive Load | Typical State |
|----------|----------|----------------|---------------|
| **Healthy Focus** | 60–120 minutes | Low to Moderate | Productive, sustainable |
| **Extended Focus** | 120–180 minutes | Moderate to High | Deep work, increasing fatigue risk |
| **High Cognitive Load** | 180–240 minutes (3–4 hours) | High | Mental fatigue beginning; diminishing returns likely |
| **Fatigue Risk** | 240+ minutes (4+ hours) | Very High | Significant fatigue; decision quality and focus quality degrading |

**Note:** Cognitive Load Awareness messages begin at 120 minutes (Extended Focus) to avoid overlap with Focused Work Reminder alerts that activate at 180+ minutes of activity.

### Message Generation System

The system generates motivational and awareness-based messages by combining phrases from four thematic libraries: **Progress**, **Reflection**, **Recovery**, and **Focus**. Each message is composed dynamically to avoid repetition and create a natural, conversational tone.

#### Phrase Library

**Progress Phrases** (celebrate focus and effort):
- "You're building momentum"
- "This focused work is valuable"
- "Deep work compounds over time"
- "You're making real progress"
- "Your effort is accumulating"
- "Sustained focus is a strength"

**Reflection Phrases** (encourage self-awareness):
- "Notice how you're working right now"
- "Reflect on what you've accomplished"
- "Your patterns reveal your priorities"
- "Be honest with yourself about your energy"
- "Consider how you're feeling"
- "Acknowledge your current state"

**Recovery Phrases** (normalize breaks and rest):
- "Breaks aren't lost time; they're investment"
- "Rest enables better thinking"
- "Recovery is part of productive work"
- "Your brain needs downtime to consolidate learning"
- "Short breaks improve decision quality"
- "Stepping away often leads to breakthrough insights"

**Focus Phrases** (reframe attention management):
- "Attention is your most valuable resource"
- "Protecting focus is an act of self-care"
- "Sustainable focus beats exhausted output"
- "Your mind needs variety to stay sharp"
- "Energy management is productivity management"
- "Intentional breaks support intentional focus"

### Message Examples by Duration

#### 90 Minutes of Continuous Focus
**Category:** Healthy Focus
**Message:** "✅ You've been focused for 90 minutes. This is solid, sustainable deep work. You're building momentum."

**Alternative Messages (dynamic generation):**
- "Your sustained focus is paying off. Notice how engaged you are."
- "90 minutes of deep work—your effort is accumulating. Keep it up."
- "You're in a productive flow. Your brain and body are working well together at this pace."

#### 180 Minutes (3 Hours) of Continuous Focus
**Category:** Extended Focus
**Message:** "⚠️ You've been focused for 3 hours. You're doing excellent deep work. A 15-minute break soon will help maintain quality."

**Alternative Messages (dynamic generation):**
- "Three hours of focused effort—be honest with yourself about your energy. A short recovery now pays dividends."
- "You're well into extended focus. Reflect on how you're feeling. Research shows a brief break soon will sharpen your thinking."
- "Your attention has been strong for 3 hours. Rest enables better thinking. Consider stepping away soon."

#### 240 Minutes (4 Hours) of Continuous Focus
**Category:** High Cognitive Load
**Message:** "⏰ You've been focused for 4 hours. Fatigue is likely affecting decision quality. A 20-minute break would help you return with fresh perspective."

**Alternative Messages (dynamic generation):**
- "Four hours is ambitious. Your mind needs variety to stay sharp. A break isn't lost time—it's investment in your next phase of work."
- "You're at high cognitive load. Acknowledge your current state: fatigue is normal at this duration. Recovery now enables breakthrough thinking."
- "Four hours of sustained work is substantial. Be honest: stepping away for 20 minutes often leads to insights you can't access when exhausted."

#### 300+ Minutes (5+ Hours) of Continuous Focus
**Category:** Fatigue Risk
**Message:** "🚨 You've been focused for 5+ hours. Fatigue is significantly affecting your output quality. A substantial break (30+ minutes) will restore your effectiveness."

**Alternative Messages (dynamic generation):**
- "Five+ hours: your brain is likely operating at reduced efficiency. Sustainable focus beats exhausted output. Step away meaningfully."
- "At this duration, your decision quality is degrading. Protect your work by resting now. Your second session will be far more valuable."
- "You've invested significant effort. Notice: continuing now returns diminishing results. Genuine recovery restores your capacity."

### Notification Behavior

- **Frequency:** Messages appear at key duration thresholds: 90 min, 180 min, 240 min, 300 min, and then every 60 minutes thereafter
- **Display:** Non-modal popup notification (does not interrupt active work)
- **Duration:** Displays for 10 seconds; auto-dismisses unless user clicks to expand
- **Expandable:** User can click message to see full details and suggested break duration
- **Trackable:** User can opt out of messages for specific categories in settings

### Integration with End-of-Day Digest

The Daily Digest includes a new **Focus Health Report** section:
- **Peak focus duration for the day** — Longest continuous session and its category
- **Focus pattern analysis** — Distribution of session durations throughout the day
- **Fatigue trend** — Whether sessions are trending toward longer or shorter durations (indicator of sustainable pace)
- **Recovery insights** — Average break duration between sessions; comparison to recommended minimums

### Differentiation from Focused Work Reminder System

| System | What It Tracks | Key Question | When It Activates |
|--------|---|---|---|
| **Focused Work Reminder** | Active session duration and idle time | Should I take a break for health? | After 3+ hours active or 3+ hours idle |
| **Cognitive Load Awareness** | Continuous focus quality and sustainability | How is my focus capacity holding up? | At 120, 180, 240+ min continuous session |

The two systems work synergistically:
- **Focused Work Reminder** answers: "Have I been working or idle long enough to need a physical break?"
- **Cognitive Load Awareness** answers: "How is the quality of my focus? Am I approaching fatigue?"

Together, they provide a complete picture of work patterns and help users optimize both engagement and sustainability.

**No conflict:** Cognitive Load messages start at 120 minutes; Focused Work Reminder alerts only trigger at 180+ minutes, eliminating notification overlap.

### Success Metrics

- **Message relevance:** ≥ 75% of users rate motivational messages as "helpful" or "insightful" (optional survey)
- **User engagement:** ≥ 60% of users who see extended focus messages take a break within 10 minutes
- **Fatigue awareness:** ≥ 70% of users report increased awareness of their focus capacity after using the system for 2 weeks
- **Reduced false alarms:** Message dismissal rate < 15% (indicating appropriate timing and relevance)

---

## Design Philosophy: Real-time Awareness vs. Passive Observation

### Evolution of the Core Philosophy

FocusGuard's original vision centered on **passive observation with end-of-day review**. However, the addition of real-time alert systems (Focused Work Reminder and Cognitive Load Awareness) represents a thoughtful expansion rather than a contradiction.

### The Distinction: Awareness ≠ Enforcement

The key principle: **Real-time notifications are information tools, not behavioral controls.**

| Approach | What It Does | FocusGuard's Stance |
|----------|-------------|---|
| **Enforcement** | Blocks sites, locks screen, prevents access | ❌ Explicitly rejected |
| **Prescriptive** | Tells you exactly what to do; guilt-based | ❌ Explicitly rejected |
| **Awareness** | Surfaces data about your current state; lets you decide | ✅ Embraced |

### Why Real-Time Alerts Work Within This Philosophy

1. **Non-modal popups** — Alerts don't interrupt active work; they notify without demanding immediate action
2. **User control** — Every alert is dismissible; users retain full autonomy
3. **Time-bounded** — Alerts auto-dismiss or require a click; they don't persist nag
4. **Informational** — Messages describe your state (duration, cognitive load) rather than prescribe actions
5. **Transparent timing** — Clear thresholds (3 hrs active, 120 min focus) help users understand why they're seeing alerts

### Examples: Awareness, Not Enforcement

**❌ Enforcement approach:**
- *"You've been working too long. Your computer is now locked for 30 minutes."*
- *"STOP! You're procrastinating. Close Reddit immediately."*

**✅ FocusGuard's awareness approach:**
- *"You've been focused for 3 hours. Research suggests a 15-minute break can sharpen your thinking."*
- *"You've been idle for 3 hours. Click anywhere to resume monitoring."*

The second set provides data and insight; it doesn't restrict or shame.

### Integration with Daily Digest Philosophy

FocusGuard's original strength is **end-of-day reflection**. Real-time alerts complement, not replace, this:
- **During work:** Gentle, dismissible awareness nudges (real-time alerts)
- **After work:** Comprehensive, detailed reflection with trends and patterns (Daily Digest)

Together, they create a two-stage system:
1. **Real-time:** "Here's what's happening now" (minimal, contextual)
2. **End-of-day:** "Here's what happened today and what it means" (comprehensive, reflective)
