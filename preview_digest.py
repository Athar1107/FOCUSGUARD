"""
preview_digest.py
-----------------
Generate and open today's Daily Digest directly — no need to run the full app.
Useful for testing the HTML template.

Usage:
    python preview_digest.py
    python preview_digest.py 2026-06-02   # specific date
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.database_layer import DatabaseLayer
from reporting.report_generator import ReportGenerator

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else None

    db = DatabaseLayer(db_path=Path("data/focusguard.db"))

    config = {
        "distracting_sites": ["reddit.com", "twitter.com", "youtube.com"],
    }

    rg = ReportGenerator(
        db=db,
        config=config,
        project_root=Path(__file__).parent,
    )

    rg.generate_and_open(date_str)
    print("Digest opened in browser.")
    db.close()

if __name__ == "__main__":
    main()
