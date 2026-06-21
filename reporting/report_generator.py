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

CATEGORY_COLORS = {
    "Work": "#d35400",          # Orange/Dark Orange
    "Education": "#1e4620",     # Dark Green (matches Education dark green background/border in screenshot)
    "Communication": "#0b3c5d", # Dark Blue
    "Utility": "#d27d2d",       # Orange/Yellow
    "Entertainment": "#782a2a", # Dark Red/Rose
    "News": "#4a2c5a",          # Purple
    "Other": "#2d3748",         # Dark Grey
}

# Standard text colors for category badges
CATEGORY_TEXT_COLORS = {
    "Work": "#fc8181",
    "Education": "#68d391",
    "Communication": "#63b3ed",
    "Utility": "#f6ad55",
    "Entertainment": "#fc8181",
    "News": "#d6bcfa",
    "Other": "#a0aec0",
}


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

    def _get_item_category(self, name: str) -> str:
        """Dynamically categorize a site or application by its name."""
        name_lower = name.lower()
        if any(k in name_lower for k in ["devenv", "visual studio", "vscode", "pycharm", "eclipse", "git", "sublime"]):
            return "Work"
        elif any(k in name_lower for k in ["slack", "discord", "messenger", "whatsapp", "teams", "zoom", "telegram", "skype"]):
            return "Communication"
        elif any(k in name_lower for k in ["chrome", "firefox", "msedge", "safari", "brave", "opera", "wikipedia", "stackoverflow", "github", "ycombinator"]):
            return "Education"
        elif any(k in name_lower for k in ["searchapp", "explorer", "taskmgr", "advinst", "advanced installer", "settings", "cmd", "powershell"]):
            return "Utility"
        elif any(k in name_lower for k in ["youtube", "tiktok", "netflix", "twitch", "vimeo", "reddit", "buzzfeed", "huffpost", "instagram", "facebook", "twitter", "x.com"]):
            return "Entertainment"
        elif any(k in name_lower for k in ["bbc.com", "cnn.com", "theguardian.com", "nytimes.com", "dailymail.co.uk"]):
            return "News"
        else:
            return "Other"

    def _get_display_name(self, site: str, app_name: str) -> str:
        """Generate a clean display name for the application list."""
        if not app_name:
            return site or "Unknown App"
        
        app_lower = app_name.lower()
        is_browser = any(b in app_lower for b in ["chrome", "edge", "firefox", "safari", "brave", "opera"])
        
        if is_browser and site:
            site_clean = site.split(".")[0].capitalize() if "." in site else site.capitalize()
            return f"{site_clean} ({app_name})"
        else:
            if "devenv" in app_lower:
                return f"Microsoft® Visual Studio® ({app_name.replace('.exe', '')})"
            elif "advinst" in app_lower:
                return f"Advanced Installer ({app_name.replace('.exe', '')})"
            elif "searchapp" in app_lower:
                return f"SearchApp ({app_name.replace('.exe', '')})"
            else:
                name_part = app_name.split(".")[0] if "." in app_name else app_name
                return f"{name_part.capitalize()} ({app_name.replace('.exe', '')})"

    def _format_duration_str(self, seconds: int) -> str:
        """Format seconds into e.g. '1h 12m 3s' or '36s'."""
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        parts = []
        if h > 0:
            parts.append(f"{h}h")
        if m > 0 or h > 0:
            parts.append(f"{m}m")
        if s > 0 or not parts:
            parts.append(f"{s}s")
        return " ".join(parts)

    def _format_duration_short(self, seconds: int) -> str:
        """Format seconds into e.g. '1h 12m' or '33m'."""
        h = seconds // 3600
        m = (seconds % 3600) // 60
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

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
        summaries_map = {row["date"]: row["confirmed_duration_secs"] + row["unconfirmed_duration_secs"] for row in weekly_raw}

        weekly_trend = []
        for d in consecutive_dates:
            secs = summaries_map.get(d, 0)
            dt_d = datetime.strptime(d, "%Y-%m-%d")
            weekly_trend.append(
                {
                    "date": d,
                    "day": dt_d.strftime("%a"),
                    "hours": round(secs / 3600.0, 1),
                }
            )

        # 6. Group and calculate app list and category breakdown for the current day
        app_durations: dict[str, int] = {}
        category_durations: dict[str, int] = {}

        for s in sessions:
            # group by app_name or site if app_name is empty
            app_key = s["app_name"] or s["site"] or "Unknown"
            app_durations[app_key] = app_durations.get(app_key, 0) + s["duration_seconds"]

            # group by category
            cat = self._get_item_category(app_key)
            category_durations[cat] = category_durations.get(cat, 0) + s["duration_seconds"]

        # Sort apps by duration descending
        sorted_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)
        max_app_duration = sorted_apps[0][1] if sorted_apps else 1

        app_list = []
        for name, secs in sorted_apps:
            # Find matching site for domain resolution in display name
            site_val = ""
            for s in sessions:
                if (s["app_name"] or s["site"]) == name:
                    site_val = s["site"]
                    break

            cat = self._get_item_category(name)
            app_list.append({
                "name": name,
                "display_name": self._get_display_name(site_val, name),
                "category": cat,
                "category_color": CATEGORY_COLORS.get(cat, "#2d3748"),
                "category_text_color": CATEGORY_TEXT_COLORS.get(cat, "#a0aec0"),
                "duration_str": self._format_duration_str(secs),
                "pct": round((secs / max_app_duration) * 100),
            })

        # Calculate category breakdown percentages for the segmented bar
        total_category_secs = sum(category_durations.values()) or 1
        category_breakdown = []
        for cat, secs in sorted(category_durations.items(), key=lambda x: x[1], reverse=True):
            pct = round((secs / total_category_secs) * 100)
            if pct > 0:
                category_breakdown.append({
                    "category": cat,
                    "percentage": pct,
                    "color": CATEGORY_COLORS.get(cat, "#2d3748"),
                    "text_color": CATEGORY_TEXT_COLORS.get(cat, "#a0aec0"),
                    "duration_str": self._format_duration_short(secs)
                })

        # Donut chart data (top 4 apps + "Other Apps" if needed)
        donut_labels = []
        donut_data = []
        donut_colors = []
        top_n = 4
        if len(sorted_apps) > top_n:
            top_apps = sorted_apps[:top_n]
            other_secs = sum(x[1] for x in sorted_apps[top_n:])
            top_apps.append(("Other Apps", other_secs))
        else:
            top_apps = sorted_apps

        for name, secs in top_apps:
            if name == "Other Apps":
                display = "Other Apps"
                color = "#f39c12"  # Golden/Yellow for "Other" in screenshot
            else:
                display = name.split(".")[0] if "." in name else name
                display = display.capitalize()
                cat = self._get_item_category(name)
                color = CATEGORY_COLORS.get(cat, "#2d3748")
            
            donut_labels.append(display)
            donut_data.append(round(secs / 60.0, 1))  # in minutes
            donut_colors.append(color)

        # 7. Total time calculations
        total_secs = confirmed_secs + unconfirmed_secs
        total_hours_val = total_secs // 3600
        total_mins_val = (total_secs % 3600) // 60
        if total_hours_val > 0:
            total_time_str = f"{total_hours_val} hr, {total_mins_val} min"
        else:
            total_time_str = f"{total_mins_val} min"

        # 8. Date navigation calculations
        all_dates = self._db.get_all_logged_dates()

        if date_str not in all_dates and date_str:
            all_dates.append(date_str)
            all_dates.sort()

        prev_date = None
        next_date = None
        if date_str in all_dates:
            idx = all_dates.index(date_str)
            if idx > 0:
                prev_date = all_dates[idx - 1]
            if idx < len(all_dates) - 1:
                next_date = all_dates[idx + 1]

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        date_header = f"Today, {day_name}"

        # 9. Render templates
        template = self._env.get_template("digest.html.j2")
        rendered = template.render(
            date=date_str,
            date_header=date_header,
            prev_date=prev_date,
            next_date=next_date,
            confirmed_count=confirmed_count,
            confirmed_duration_mins=confirmed_mins,
            unconfirmed_count=unconfirmed_count,
            unconfirmed_duration_mins=unconfirmed_mins,
            total_time_str=total_time_str,
            app_list=app_list,
            category_breakdown=category_breakdown,
            donut_labels=donut_labels,
            donut_data=donut_data,
            donut_colors=donut_colors,
            sessions=[self._format_session_row(s) for s in sessions],
            hourly_buckets=hourly_buckets,
            top_sites=formatted_top_sites,
            weekly_trend=weekly_trend,
        )

        # 10. Write report file
        report_file = self._reports_dir / f"digest_{date_str}.html"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(rendered)

        logger.info("Digest report written successfully to: %s", report_file)

        # 11. Open in standard browser
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
