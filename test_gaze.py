"""
test_gaze.py
------------
Visual gaze detection test — shows live webcam feed with:
  - Face mesh landmarks drawn on your face
  - Eye contours highlighted
  - LOOKING / NOT_LOOKING status on screen in large text
  - EAR value displayed

Press Q to quit.

Usage:
    python test_gaze.py
"""

import math
import json
import sys
import time
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = Path("data/models/face_landmarker.task")

def ensure_model():
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.exists():
        print("Downloading FaceLandmarker model (~29 MB) — one time only...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Done.\n")

# ---------------------------------------------------------------------------
# Landmark indices
# ---------------------------------------------------------------------------
_LEFT_EYE   = [362, 385, 387, 263, 373, 380]
_RIGHT_EYE  = [33,  160, 158, 133, 153, 144]
_LEFT_IRIS  = [474, 475, 476, 477]
_RIGHT_IRIS = [469, 470, 471, 472]

_EAR_CLOSED_THRESHOLD_DEFAULT = 0.20
_IRIS_OFFSET_THRESHOLD_DEFAULT = 0.40
_GAZE_STABLE_FRAMES_DEFAULT = 2


def _load_tuning():
    config_path = Path("data/config.json")
    tuning = {
        "gaze_ear_closed_threshold": _EAR_CLOSED_THRESHOLD_DEFAULT,
        "gaze_iris_offset_threshold": _IRIS_OFFSET_THRESHOLD_DEFAULT,
        "gaze_stable_frames": _GAZE_STABLE_FRAMES_DEFAULT,
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError):
        return tuning

    for key, default in tuning.items():
        try:
            value = config.get(key, default)
            tuning[key] = float(value) if key != "gaze_stable_frames" else max(int(value), 1)
        except (TypeError, ValueError):
            tuning[key] = default

    return tuning

# All face contour points for drawing the mesh
_FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109
]

def dist(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def ear(lm, idx, w, h):
    pts = [(int(lm[i].x*w), int(lm[i].y*h)) for i in idx]
    v = dist(pts[1], pts[5]) + dist(pts[2], pts[4])
    hd = dist(pts[0], pts[3])
    return v / (2*hd) if hd > 0 else 0.0

def iris_off(lm, eye_idx, iris_idx, w, h):
    ep  = [(lm[i].x*w, lm[i].y*h) for i in eye_idx]
    ip  = [(lm[i].x*w, lm[i].y*h) for i in iris_idx]
    ecx = sum(p[0] for p in ep) / len(ep)
    icx = sum(p[0] for p in ip) / len(ip)
    ew  = dist(ep[0], ep[3])
    return abs(icx - ecx) / ew if ew > 0 else 0.0

def classify(lm, w, h, tuning):
    le  = ear(lm, _LEFT_EYE,  w, h)
    re  = ear(lm, _RIGHT_EYE, w, h)
    avg_ear = (le + re) / 2.0
    avg_off = 0.0
    if len(lm) > 477:
        avg_off = (iris_off(lm, _LEFT_EYE,  _LEFT_IRIS,  w, h) +
                   iris_off(lm, _RIGHT_EYE, _RIGHT_IRIS, w, h)) / 2.0
    looking = (
        avg_ear >= tuning["gaze_ear_closed_threshold"] and
        avg_off <= tuning["gaze_iris_offset_threshold"]
    )
    return looking, avg_ear, avg_off

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_landmarks(frame, lm, w, h, cv2):
    """Draw face mesh dots."""
    for point in lm:
        x, y = int(point.x * w), int(point.y * h)
        cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

def draw_eye_contour(frame, lm, idx, w, h, color, cv2):
    """Draw a polygon around an eye."""
    pts = [(int(lm[i].x*w), int(lm[i].y*h)) for i in idx]
    for j in range(len(pts)):
        cv2.line(frame, pts[j], pts[(j+1) % len(pts)], color, 1)

def draw_iris(frame, lm, idx, w, h, color, cv2):
    """Draw iris circle."""
    pts = [(int(lm[i].x*w), int(lm[i].y*h)) for i in idx]
    cx  = sum(p[0] for p in pts) // len(pts)
    cy  = sum(p[1] for p in pts) // len(pts)
    r   = int(dist(pts[0], pts[2]) / 2) + 2
    cv2.circle(frame, (cx, cy), r, color, 2)

def put_status(frame, looking, ear_val, off_val, cv2):
    """Overlay the gaze status text on the frame."""
    h, w = frame.shape[:2]

    if looking:
        label  = "LOOKING"
        color  = (0, 220, 0)    # green
        bg     = (0, 80, 0)
    else:
        label  = "NOT LOOKING"
        color  = (0, 60, 255)   # red
        bg     = (0, 0, 100)

    # Background banner
    cv2.rectangle(frame, (0, 0), (w, 60), bg, -1)

    # Main label
    cv2.putText(frame, label, (12, 44),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3, cv2.LINE_AA)

    # EAR + offset stats bottom-left
    stats = f"EAR: {ear_val:.2f}  |  Iris offset: {off_val:.2f}"
    cv2.putText(frame, stats, (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

    # Hint bottom-right
    cv2.putText(frame, "Press Q to quit", (w - 160, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        import cv2
    except ImportError:
        print("OpenCV not installed. Run: pip install opencv-python-headless")
        sys.exit(1)

    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe.tasks.python.core import base_options as mp_base
    except ImportError:
        print("MediaPipe not installed. Run: pip install mediapipe")
        sys.exit(1)

    ensure_model()

    tuning = _load_tuning()
    print(
        "Loaded gaze tuning: "
        f"EAR>={tuning['gaze_ear_closed_threshold']:.2f}, "
        f"Iris<={tuning['gaze_iris_offset_threshold']:.2f}, "
        f"stable_frames={tuning['gaze_stable_frames']}"
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    base_opts = mp_base.BaseOptions(model_asset_path=str(MODEL_PATH))
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=base_opts,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
        num_faces=1,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(opts)

    print("Gaze test running — look at screen, look away, cover camera.")
    print("Press Q in the webcam window to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)          # mirror so it feels natural
        h, w  = frame.shape[:2]
        rgb   = frame[:, :, ::-1].copy()

        mp_img    = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        detection = landmarker.detect(mp_img)

        looking  = False
        ear_val  = 0.0
        off_val  = 0.0

        if detection.face_landmarks:
            lm = detection.face_landmarks[0]

            # Draw all mesh dots
            draw_landmarks(frame, lm, w, h, cv2)

            # Draw eye contours — green when looking, red when not
            eye_color = (0, 220, 0) if looking else (60, 60, 255)
            draw_eye_contour(frame, lm, _LEFT_EYE,  w, h, (0, 255, 255), cv2)
            draw_eye_contour(frame, lm, _RIGHT_EYE, w, h, (0, 255, 255), cv2)

            # Draw iris circles
            if len(lm) > 477:
                draw_iris(frame, lm, _LEFT_IRIS,  w, h, (255, 100, 0), cv2)
                draw_iris(frame, lm, _RIGHT_IRIS, w, h, (255, 100, 0), cv2)

            looking, ear_val, off_val = classify(lm, w, h, tuning)

        put_status(frame, looking, ear_val, off_val, cv2)

        cv2.imshow("FocusGuard — Gaze Test (Q to quit)", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    landmarker.close()
    cv2.destroyAllWindows()
    print("Done.")

if __name__ == "__main__":
    main()
