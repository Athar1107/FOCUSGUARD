"""
flask_server.py
---------------
Local HTTP server that receives URL updates from the browser extension.

Routes:
  POST /url   — receives {url, timestamp, browser}, writes to UrlState
  GET  /ping  — health check for the browser extension

Security:
  - Binds to 127.0.0.1 only (never 0.0.0.0)
  - Rejects requests from any remote address with HTTP 403
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from flask import Flask, jsonify, request

from bridge.url_state import UrlState

logger = logging.getLogger(__name__)

# Suppress Flask's default request logging to keep the console clean
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


class FlaskServer:
    """
    Wraps the Flask app and runs it in a daemon thread.
    """

    def __init__(self, config: dict, url_state: UrlState) -> None:
        self._config = config
        self._url_state = url_state
        self._port: int = config.get("flask_port", 5678)
        self._app = self._build_app()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Flask app factory
    # ------------------------------------------------------------------

    def _build_app(self) -> Flask:
        app = Flask(__name__)
        app.config["PROPAGATE_EXCEPTIONS"] = False

        url_state = self._url_state  # capture for closure

        @app.before_request
        def _check_localhost():
            """Reject any request not originating from 127.0.0.1."""
            remote = request.remote_addr
            if remote not in ("127.0.0.1", "::1"):
                logger.warning("Rejected request from non-localhost: %s", remote)
                return jsonify({"error": "forbidden"}), 403

        @app.post("/url")
        def receive_url():
            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "invalid JSON"}), 400

            url = data.get("url", "").strip()
            timestamp = data.get("timestamp", "").strip()

            if not url or not timestamp:
                return jsonify({"error": "missing url or timestamp"}), 400

            url_state.set_url(url)
            logger.debug("Extension URL received: %s", url)

            # Determine if the URL is distracting (for the response payload)
            from bridge._site_checker import is_distracting_url
            distracting = is_distracting_url(url, self._config.get("distracting_sites", []))
            tier = "distracting" if distracting else "clean"

            return jsonify({"status": "logged", "tier": tier}), 200

        @app.get("/ping")
        def ping():
            return jsonify({"status": "ok"}), 200

        return app

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._serve,
            name="FlaskServer",
            daemon=True,
        )
        self._thread.start()
        logger.info("FlaskServer started on 127.0.0.1:%d", self._port)

    def _serve(self) -> None:
        try:
            self._app.run(
                host="127.0.0.1",
                port=self._port,
                debug=False,
                use_reloader=False,
                threaded=False,
            )
        except OSError as exc:
            logger.error(
                "FlaskServer failed to bind on port %d: %s", self._port, exc
            )

    def stop(self) -> None:
        # Flask dev server doesn't have a clean shutdown API;
        # the daemon thread will be killed when the main process exits.
        logger.info("FlaskServer stopping (daemon thread will exit with process)")
