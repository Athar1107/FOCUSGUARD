"""
_site_checker.py
----------------
Shared utility used by both the Flask server (for response payload)
and the ActivityMonitor (for signal evaluation).
"""

from __future__ import annotations

from urllib.parse import urlparse


def _domain_matches(candidate: str, pattern: str) -> bool:
    candidate = candidate.lower()
    pattern = pattern.lower()
    return candidate == pattern or candidate.endswith(f".{pattern}")


def is_distracting_url(url: str, distracting_sites: list[str]) -> bool:
    """Return True if the URL's domain matches any entry in distracting_sites."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.hostname or "").removeprefix("www.")
    except Exception:
        return False

    for pattern in distracting_sites:
        if _domain_matches(host, pattern):
            return True
    return False
