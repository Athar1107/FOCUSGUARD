"""
check_sessions.py
-----------------
Shows all sessions logged today in the database.

Usage:
    python check_sessions.py
"""

import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.database_layer import DatabaseLayer

db = DatabaseLayer(db_path=Path("data/focusguard.db"))
today = datetime.date.today().isoformat()
rows = db.get_sessions_for_date(today)

print(f"\n{'='*60}")
print(f"  FocusGuard Sessions - {today}")
print(f"{'='*60}")

if not rows:
    print("  No sessions logged today yet.")
    print("\n  Make sure:")
    print("  1. python main.py is running in tray")
    print("  2. You opened a distracting site (reddit.com etc)")
    print("  3. You didn't touch keyboard/mouse for 30+ seconds")
    print("  4. You looked at the screen (webcam on)")
else:
    confirmed   = [r for r in rows if r["tier"] == "confirmed"]
    unconfirmed = [r for r in rows if r["tier"] == "unconfirmed"]
    print(f"\n  Total sessions : {len(rows)}")
    print(f"  Confirmed      : {len(confirmed)}  (Tier 2 - all 3 signals)")
    print(f"  Unconfirmed    : {len(unconfirmed)}  (Tier 1 - window + idle only)")
    print(f"\n  {'TIME':<10} {'TIER':<14} {'SITE':<22} {'GAZE':<14} {'DURATION'}")
    print(f"  {'-'*70}")
    for r in rows:
        print(f"  {r['started_at'][11:19]:<10} {r['tier']:<14} {r['site']:<22} {r['gaze_status']:<14} {r['duration_seconds']}s")

print(f"\n{'='*60}\n")
db.close()
