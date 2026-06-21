"""
gaze_detector.py
----------------
Webcam-based gaze detection using OpenCV + MediaPipe FaceLandmarker (Tasks API).

Works with MediaPipe 0.10+ which replaced mp.solutions with mp.tasks.

Algorithm:
  1. Capture frame from webcam via OpenCV
  2. Pass to MediaPipe FaceLandmarker → 478 facial landmarks (incl. iris)
  3. Calculate Eye Aspect Ratio (EAR) — are eyes open?
  4. Calculate iris offset — is user looking at the screen?
  5. Classify as LOOKING or NOT_LOOKING
  6. Emit binary result to SessionManager every gaze_poll_interval_seconds

Privacy guarantee:
  - Raw frames are NEVER stored, queued, or passed to other components
  - Only the binary LOOKING/NOT_LOOKING result leaves this module
  - Frame buffer reference is deleted after every single capture
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core.event_types import GazeSignal
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MediaPipe FaceLandmarker model — downloaded once and cached locally
# ---------------------------------------------------------------------------
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_FILENAME = "face_landmarker.task"

def _get_model_path() -> Path:
    """Return path to the cached model file, downloading it if necessary."""
    cache_dir = Path(__file__).parent.parent / "data" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / _MODEL_FILENAME
    if not model_path.exists():
        logger.info("Downloading FaceLandmarker model to %s ...", model_path)
        urllib.request.urlretrieve(_MODEL_URL, model_path)
        logger.info("Model downloaded successfully")
    return model_path


# ---------------------------------------------------------------------------
# Landmark indices (MediaPipe 478-point model)
# ---------------------------------------------------------------------------
_LEFT_EYE  = [362, 385, 387, 263, 373, 380]
_RIGHT_EYE = [33,  160, 158, 133, 153, 144]
_LEFT_IRIS  = [474, 475, 476, 477]
_RIGHT_IRIS = [469, 470, 471, 472]

_EAR_CLOSED_THRESHOLD_DEFAULT = 0.20   # below → eyes closed
_IRIS_OFFSET_THRESHOLD_DEFAULT = 0.40   # above → looking sideways
_GAZE_STABLE_FRAMES_DEFAULT = 2


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(p1, p2) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _float_config(config: dict, key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_config(config: dict, key: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(config.get(key, default)), minimum)
    except (TypeError, ValueError):
        return max(default, minimum)


def _ear(landmarks, indices: list[int], w: int, h: int) -> float:
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    v1 = _dist(pts[1], pts[5])
    v2 = _dist(pts[2], pts[4])
    hd = _dist(pts[0], pts[3])
    return (v1 + v2) / (2.0 * hd) if hd > 0 else 0.0


def _iris_offset(landmarks, eye_idx: list[int], iris_idx: list[int],
                 w: int, h: int) -> float:
    eye_pts  = [(landmarks[i].x * w, landmarks[i].y * h) for i in eye_idx]
    iris_pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in iris_idx]
    eye_cx   = sum(p[0] for p in eye_pts)  / len(eye_pts)
    iris_cx  = sum(p[0] for p in iris_pts) / len(iris_pts)
    eye_w    = _dist(eye_pts[0], eye_pts[3])
    return abs(iris_cx - eye_cx) / eye_w if eye_w > 0 else 0.0


def _classify(landmarks, w: int, h: int) -> GazeSignal:
    return _classify_with_thresholds(
        landmarks,
        w,
        h,
        ear_closed_threshold=_EAR_CLOSED_THRESHOLD_DEFAULT,
        iris_offset_threshold=_IRIS_OFFSET_THRESHOLD_DEFAULT,
    )


def _classify_with_thresholds(
    landmarks,
    w: int,
    h: int,
    *,
    ear_closed_threshold: float,
    iris_offset_threshold: float,
) -> GazeSignal:
    left_ear  = _ear(landmarks, _LEFT_EYE,  w, h)
    right_ear = _ear(landmarks, _RIGHT_EYE, w, h)
    if (left_ear + right_ear) / 2.0 < ear_closed_threshold:
        return GazeSignal.NOT_LOOKING

    if len(landmarks) > 477:
        lo = _iris_offset(landmarks, _LEFT_EYE,  _LEFT_IRIS,  w, h)
        ro = _iris_offset(landmarks, _RIGHT_EYE, _RIGHT_IRIS, w, h)
        if (lo + ro) / 2.0 > iris_offset_threshold:
            return GazeSignal.NOT_LOOKING

    return GazeSignal.LOOKING


# ---------------------------------------------------------------------------
# GazeDetector
# ---------------------------------------------------------------------------

class GazeDetector:
    """
    Background thread: captures webcam frames, runs FaceLandmarker,
    emits binary gaze signals to SessionManager.
    """

    def __init__(
        self,
        config: dict,
        session_manager: SessionManager,
        on_error: Optional[Callable[[str], None]] = None,
        on_error_cleared: Optional[Callable[[], None]] = None,
    ) -> None:
        self._config          = config
        self._session_manager = session_manager
        self._on_error        = on_error
        self._on_error_cleared = on_error_cleared

        self._enabled     = config.get("webcam_enabled", True)
        self._stop_event  = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock        = threading.Lock()

        self._last_signal: Optional[GazeSignal] = None
        self._last_emit   = 0.0
        self._webcam_ok   = False
        self._pending_signal: Optional[GazeSignal] = None
        self._pending_streak = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info("GazeDetector starting (enabled=%s)", self._enabled)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="GazeDetector", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        logger.info("GazeDetector stopping")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=6)
            self._thread = None

    def enable(self) -> None:
        with self._lock:
            self._enabled = True
        logger.info("GazeDetector enabled")

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
        self._session_manager.on_gaze_signal(GazeSignal.TOGGLED_OFF)
        logger.info("GazeDetector disabled")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            import cv2
        except ImportError:
            logger.error("OpenCV not installed — gaze detection unavailable")
            self._session_manager.on_gaze_signal(GazeSignal.UNAVAILABLE)
            if self._on_error:
                self._on_error("OpenCV not installed")
            return

        try:
            # Suppress MediaPipe C++ stderr noise before import
            import os as _os
            _os.environ.setdefault("GLOG_minloglevel", "3")
            _os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

            import mediapipe as mp
            from mediapipe.tasks.python import vision as mp_vision
            from mediapipe.tasks.python.core import base_options as mp_base
        except ImportError:
            logger.error("MediaPipe not installed — gaze detection unavailable")
            self._session_manager.on_gaze_signal(GazeSignal.UNAVAILABLE)
            if self._on_error:
                self._on_error("MediaPipe not installed")
            return

        # Download / locate model
        try:
            model_path = _get_model_path()
        except Exception as exc:
            logger.error("Failed to download FaceLandmarker model: %s", exc)
            self._session_manager.on_gaze_signal(GazeSignal.UNAVAILABLE)
            if self._on_error:
                self._on_error("Model download failed — check internet connection")
            return

        # Build FaceLandmarker (Tasks API)
        base_opts    = mp_base.BaseOptions(model_asset_path=str(model_path))
        landmarker_opts = mp_vision.FaceLandmarkerOptions(
            base_options=base_opts,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1,
        )

        cap        = None
        landmarker = None

        while not self._stop_event.is_set():
            with self._lock:
                enabled = self._enabled

            # ── Webcam toggled OFF ─────────────────────────────────────
            if not enabled:
                if cap is not None:
                    cap.release()
                    cap = None
                if landmarker is not None:
                    landmarker.close()
                    landmarker = None
                self._stop_event.wait(timeout=1.0)
                continue

            # ── Acquire webcam ─────────────────────────────────────────
            if cap is None or not cap.isOpened():
                idx = self._config.get("webcam_device_index", 0)
                cap = cv2.VideoCapture(idx)
                if not cap.isOpened():
                    cap = None
                    retry = self._config.get("gaze_retry_interval_secs", 30)
                    logger.warning("Webcam %d unavailable — retry in %ds", idx, retry)
                    self._webcam_ok = False
                    self._session_manager.on_gaze_signal(GazeSignal.UNAVAILABLE)
                    if self._on_error:
                        self._on_error("Webcam unavailable — gaze detection paused")
                    self._stop_event.wait(timeout=retry)
                    continue
                else:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    if not self._webcam_ok:
                        self._webcam_ok = True
                        logger.info("Webcam acquired")
                        if self._on_error_cleared:
                            self._on_error_cleared()

            # ── Create landmarker if needed ────────────────────────────
            if landmarker is None:
                try:
                    landmarker = mp_vision.FaceLandmarker.create_from_options(
                        landmarker_opts
                    )
                except Exception as exc:
                    logger.error("FaceLandmarker init failed: %s", exc)
                    self._stop_event.wait(timeout=5.0)
                    continue

            # ── Capture + classify ─────────────────────────────────────
            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    cap = None
                    continue

                h, w    = frame.shape[:2]
                rgb     = frame[:, :, ::-1].copy()
                del frame   # discard raw frame immediately

                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB, data=rgb
                )
                del rgb     # discard RGB copy immediately

                detection = landmarker.detect(mp_image)

                if detection.face_landmarks:
                    lm     = detection.face_landmarks[0]
                    signal = _classify_with_thresholds(
                        lm,
                        w,
                        h,
                        ear_closed_threshold=_float_config(
                            self._config,
                            "gaze_ear_closed_threshold",
                            _EAR_CLOSED_THRESHOLD_DEFAULT,
                        ),
                        iris_offset_threshold=_float_config(
                            self._config,
                            "gaze_iris_offset_threshold",
                            _IRIS_OFFSET_THRESHOLD_DEFAULT,
                        ),
                    )
                else:
                    signal = GazeSignal.NOT_LOOKING

                stable_frames = _int_config(
                    self._config,
                    "gaze_stable_frames",
                    _GAZE_STABLE_FRAMES_DEFAULT,
                )
                if signal == self._pending_signal:
                    self._pending_streak += 1
                else:
                    self._pending_signal = signal
                    self._pending_streak = 1

                # Emit at configured interval or on state change
                now    = time.monotonic()
                period = self._config.get("gaze_poll_interval_seconds", 3)
                should_emit = False
                if self._last_signal is None:
                    should_emit = self._pending_streak >= stable_frames
                elif signal == self._last_signal:
                    should_emit = now - self._last_emit >= period
                elif self._pending_streak >= stable_frames:
                    should_emit = True

                if should_emit:
                    self._session_manager.on_gaze_signal(signal)
                    self._last_signal = signal
                    self._last_emit   = now
                    logger.debug("Gaze: %s", signal.value)

            except Exception as exc:
                logger.error("GazeDetector frame error: %s", exc)
                if cap:
                    cap.release()
                    cap = None

            # ── Sleep between frames ───────────────────────────────────
            fps   = max(self._config.get("gaze_fps", 5), 1)
            self._stop_event.wait(timeout=1.0 / fps)

        # ── Cleanup ───────────────────────────────────────────────────
        if cap:
            cap.release()
        if landmarker:
            landmarker.close()
        logger.debug("GazeDetector thread exited cleanly")
