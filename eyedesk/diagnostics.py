"""Έλεγχος του πραγματικού .exe χωρίς κάμερα, πλήκτρα ή αλλαγές στο registry.

Τα συνθετικά μαύρα frames ελέγχουν και τη φόρτωση των native MediaPipe DLLs.
Ο έλεγχος εκτελείται μόνο όταν ζητηθεί ρητά με --self-test REPORT.json.
"""
import json
from pathlib import Path
import sys
import traceback


def model_check():
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from .models import load_model_buffers
    buffers = load_model_buffers()
    blank = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((480, 640, 3), np.uint8))
    with vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=buffers["hand_landmarker"]), num_hands=2)) as hands:
        count_hands = len(hands.detect(blank).hand_landmarks)
    with vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_buffer=buffers["face_landmarker"]), num_faces=2,
        output_facial_transformation_matrixes=True)) as faces:
        count_faces = len(faces.detect(blank).face_landmarks)
    assert count_hands == 0 and count_faces == 0
    return dict(opencv=cv2.__version__, mediapipe=mp.__version__, models="loaded and inferred", camera_opened=False)


def self_test(report_path):
    from . import __version__
    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    result = dict(version=__version__, frozen=bool(getattr(sys, "frozen", False)), python=sys.version, ok=False)
    app = None
    try:
        result.update(model_check())
        from .app import App
        class NoStartup:
            def current_command(self):
                return None
            def set_enabled(self, value):
                raise AssertionError("Self-test must never write startup registry")
        app = App(config_path=report.parent / "self-test-unused-settings.json", startup_api=NoStartup())
        pages = []
        for name in app.pages:
            app.show_page(name)
            app.update()
            assert app.pages[name].winfo_ismapped()
            pages.append(name)
        assert not app.live.get() and app.worker is None
        assert hasattr(app, "nav_logo"), "Missing bundled logo"
        result.update(pages=pages, logo=True, audio_commands=False, ok=True)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if app is not None:
            app.close()
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
