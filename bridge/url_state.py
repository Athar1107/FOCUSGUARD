"""
url_state.py
------------
Thread-safe shared variable holding the most recently received browser URL.

The Flask server writes to it; the ActivityMonitor reads from it on each
poll cycle. This avoids direct cross-thread calls into the SessionManager
from the Flask request thread.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class UrlState:
    """
    Holds the latest URL received from the browser extension.

    Attributes:
        _url      : the URL string (or None if never received)
        _timestamp: epoch time of last update
        _lock     : protects both fields
    """

    def __init__(self) -> None:
        self._url: Optional[str] = None
        self._timestamp: float = 0.0
        self._lock = threading.Lock()

    def set_url(self, url: str) -> None:
        """Called by the Flask handler when a new URL arrives."""
        with self._lock:
            self._url = url
            self._timestamp = time.monotonic()

    def get_url(self, max_age_seconds: float = 5.0) -> Optional[str]:
        """
        Return the latest URL if it was received within max_age_seconds,
        otherwise return None (treat extension as absent / stale).
        """
        with self._lock:
            if self._url is None:
                return None
            age = time.monotonic() - self._timestamp
            if age > max_age_seconds:
                return None
            return self._url

    def clear(self) -> None:
        with self._lock:
            self._url = None
            self._timestamp = 0.0
