"""
seed_data.py
------------
Seeds realistic fake session data into the local SQLite database.
Use this to test the Daily Digest without waiting for real sessions.

Creates:
  - 7 days of historical data (for the weekly trend chart)
  - Today's data with both confirmed and unconfirmed sessions
  - A mix of confirmed (tier 2) and unconfirmed (tier 1) sessions

Usage:
    python seed_data.py
"""

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.database_layer import DatabaseLayer
from core.event_types import GazeSignal, SessionRecord, SessionTier

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SITES = [
    "reddit.com", "twitter.com", "youtube.com",
    "instagram.com", "news.ycombinator.com", "bbc.com",
]
APP_NAME = "chrome.exe"

def make_session(
    start: datetime,
    duration_secs: int,
    site: str,
    tier: SessionTier,
    gaze: GazeSignal,
) -> SessionRecord:
    end = start + timedelta(seconds=duration_secs)
    return SessionRecord(
        started_at=start,
        ended_at=end,
        site=site,
        app_name=APP_NAME,
        tier=tier,
        window_signal=True,
        idle_signal=True,
        gaze_signal=(gaze == GazeSignal.LOOKING),
        gaze_status=gaze,
    )

def seed_day(db: DatabaseLayer, day_offset: int, num_confirmed: int, num_unconfirmed: int):
    """Seed sessions for a day relative to today (0 = today, -1 = yesterday, etc.)"""
    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) + timedelta(days=day_offset)

    # Spread sessions across work hours (9am–6pm)
    work_minutes = list(range(0, 9 * 60))   # 0–540 minutes from 9am

    used_slots = set()

    def pick_slot(duration_secs):
        for _ in range(100):
            start_offset = random.choice(work_minutes)
            if start_offset not in used_slots:
                used_slots.add(start_offset)
                return base_date + timedelta(minutes=start_offset)
        return base_date + timedelta(minutes=random.randint(0, 500))

    # Confirmed sessions (all 3 signals)
    for _ in range(num_confirmed):
        duration = random.randint(120, 600)   # 2–10 minutes
        start    = pick_slot(duration)
        site     = random.choice(SITES)
        session  = make_session(start, duration, site, SessionTier.CONFIRMED, GazeSignal.LOOKING)
        db.write_session(session)

    # Unconfirmed sessions (webcam off or not looking)
    for _ in range(num_unconfirmed):
        duration = random.randint(30, 300)    # 30s–5 minutes
        start    = pick_slot(duration)
        site     = random.choice(SITES)
        gaze     = random.choice([GazeSignal.NOT_LOOKING, GazeSignal.TOGGLED_OFF])
        session  = make_session(start, duration, site, SessionTier.UNCONFIRMED, gaze)
        db.write_session(session)

def main():
    db_path = Path("data/focusguard.db")
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True)

    db = DatabaseLayer(db_path=db_path)
    print(f"Seeding data into {db_path}\n")

    # Past 6 days (historical trend)
    for offset in range(-6, 0):
        confirmed   = random.randint(2, 6)
        unconfirmed = random.randint(1, 4)
        seed_day(db, offset, confirmed, unconfirmed)
        date_str = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%d")
        print(f"  {date_str}  confirmed={confirmed}  unconfirmed={unconfirmed}")

    # Today — richer data
    seed_day(db, 0, num_confirmed=4, num_unconfirmed=3)
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"  {today}  confirmed=4  unconfirmed=3  <- today\n")

    db.close()
    print("Done. Run the app and click 'Open Today's Digest' from the tray.")
    print("Or run: python preview_digest.py")

if __name__ == "__main__":
    main()
