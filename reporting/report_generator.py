"""
report_generator.py
-------------------
Queries the SQLite database and renders local, offline-capable Jinja2 HTML digests.
"""

from __future__ import annotations

import json
import logging
import shutil
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from core.database_layer import DatabaseLayer

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Renders daily distraction summaries using Jinja2 and local Chart.js
    assets, and automatically launches the reports in the default browser.
    """

    def __init__(self, db: DatabaseLayer, config: dict, project_root: Path) -> None:
        self._db = db
        self._config = config
        self._project_root = project_root

        # Resolve paths to align with database directory location
        self._reports_dir = self._db.db_path.parent / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        self._template_dir = self._project_root / "reporting" / "templates"
        self._env = Environment(loader=FileSystemLoader(str(self._template_dir)))

    def generate_and_open(self, date_str: Optional[str] = None) -> None:
        """
        Query sessions and summaries, generate the digest HTML, and open it.
        date_str format: YYYY-MM-DD (defaults to local today)
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        logger.info("Generating HTML digest report for %s", date_str)

        # 1. Ensure Chart.js is placed next to the HTML report for offline loading
        self._ensure_assets()

        # 2. Query sessions and summaries
        sessions = self._db.get_sessions_for_date(date_str)
        summary = self._db.get_daily_summary(date_str)

        # 3. Compile session stats
        confirmed_count = 0
        confirmed_secs = 0
        unconfirmed_count = 0
        unconfirmed_secs = 0
        top_sites = []

        if summary:
            confirmed_count = summary["confirmed_count"]
            confirmed_secs = summary["confirmed_duration_secs"]
            unconfirmed_count = summary["unconfirmed_count"]
            unconfirmed_secs = summary["unconfirmed_duration_secs"]
            top_sites = json.loads(summary["top_sites"] or "[]")
        else:
            # Fallback manual aggregation if summary row doesn't exist
            sites_map: dict[str, int] = {}
            for s in sessions:
                dur = s["duration_seconds"]
                if s["tier"] == "confirmed":
                    confirmed_count += 1
                    confirmed_secs += dur
                else:
                    unconfirmed_count += 1
                    unconfirmed_secs += dur
                sites_map[s["site"]] = sites_map.get(s["site"], 0) + dur

            top_sites = [
                {"site": k, "duration_secs": v}
                for k, v in sorted(sites_map.items(), key=lambda item: item[1], reverse=True)
            ]

        confirmed_mins = round(confirmed_secs / 60.0, 1)
        unconfirmed_mins = round(unconfirmed_secs / 60.0, 1)

        # Convert top site durations from seconds to minutes for clean reporting
        formatted_top_sites = [
            {"site": s["site"], "duration_mins": round(float(s["duration_secs"]) / 60.0, 1)}
            for s in top_sites
        ]

        # 4. Generate hourly distraction heatmap buckets (24 hours) in local time
        hourly_buckets = [0.0] * 24
        for s in sessions:
            if s["tier"] == "confirmed":
                try:
                    # started_at is ISO UTC
                    dt_utc = datetime.strptime(s["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )
                    local_dt = dt_utc.astimezone()  # Convert to system local timezone
                    hour = local_dt.hour
                    hourly_buckets[hour] += s["duration_seconds"] / 60.0
                except Exception as exc:
                    logger.debug("Failed to calculate hour for session started_at: %s", exc)

        # Round values for display
        hourly_buckets = [round(h, 1) for h in hourly_buckets]

        # 5. Generate past 7 days trend data (filling in gaps with 0)
        try:
            end_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            end_date = datetime.now()

        # Build list of 7 consecutive dates
        consecutive_dates = [(end_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

        # Get summaries from DB
        weekly_raw = self._db.get_weekly_summaries(date_str)
        summaries_map = {row["date"]: row["confirmed_duration_secs"] for row in weekly_raw}

        weekly_trend = []
        for d in consecutive_dates:
            secs = summaries_map.get(d, 0)
            weekly_trend.append(
                {
                    "date": d,
                    "confirmed_duration_mins": round(secs / 60.0, 1),
                }
            )

        # 6. Render templates
        template = self._env.get_template("digest.html.j2")
        rendered = template.render(
            date=date_str,
            confirmed_count=confirmed_count,
            confirmed_duration_mins=confirmed_mins,
            unconfirmed_count=unconfirmed_count,
            unconfirmed_duration_mins=unconfirmed_mins,
            sessions=[self._format_session_row(s) for s in sessions],
            hourly_buckets=hourly_buckets,
            top_sites=formatted_top_sites,
            weekly_trend=weekly_trend,
        )

        # 7. Write report file
        report_file = self._reports_dir / f"digest_{date_str}.html"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(rendered)

        logger.info("Digest report written successfully to: %s", report_file)

        # 8. Open in standard browser
        webbrowser.open(report_file.as_uri())

    def _ensure_assets(self) -> None:
        """Verify and copy static Chart.js assets next to the report templates."""
        dest_chart_js = self._reports_dir / "chart.min.js"
        if not dest_chart_js.exists():
            src_chart_js = self._project_root / "assets" / "chart.min.js"
            if src_chart_js.exists():
                try:
                    shutil.copy(src_chart_js, dest_chart_js)
                    logger.info("Copied chart.min.js static asset to reports folder")
                except Exception as exc:
                    logger.error("Failed to copy static Chart.js asset: %s", exc)
            else:
                logger.warning("Bundled Chart.js asset is missing from %s", src_chart_js)

    def _format_session_row(self, s: dict) -> dict:
        """Format database rows for pretty presentation in HTML template."""
        try:
            # Convert ISO UTC string to local 12-hour AM/PM format
            dt_utc = datetime.strptime(s["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            time_str = dt_utc.astimezone().strftime("%I:%M %p")
        except Exception:
            time_str = s["started_at"]

        dur_mins = round(s["duration_seconds"] / 60.0, 1)

        return {
            "time": time_str,
            "site": s["site"],
            "app_name": s["app_name"],
            "duration_mins": dur_mins,
            "tier": s["tier"],
            "gaze_status": s["gaze_status"],
        }
