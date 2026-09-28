"""Integration tests της GUI με συνθετικά frames και ψεύτικο autostart.

Δεν ανοίγουμε κάμερα, δεν στέλνουμε πλήκτρα, δεν αλλάζουμε πραγματικό registry.
Απαιτούνται Windows με Tk. Τα προσωρινά JSON μένουν στο .local/tests.
"""
import ctypes
import json
import os
from pathlib import Path
import time
import unittest
import uuid
from unittest.mock import patch

import numpy as np

from eyedesk.app import App
from eyedesk.logic import Hand
from eyedesk.settings import HAND_LABELS, VOLUME_LABELS


class FakeStartup:
    value = None

    def current_command(self):
        return self.value

    def set_enabled(self, value):
        self.value = "mock startup" if value else None


@unittest.skipUnless(os.name == "nt", "Windows UI")
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parent.parent / ".local" / "tests" / f"{uuid.uuid4().hex}.json"
        self.startup = FakeStartup()
        self.app = App(config_path=self.path, startup_api=self.startup)
        self.app.settings["sound"] = False
        self.app.sound.set(False)
        self.app.update()

    def tearDown(self):
        if not self.app.closed:
            self.app.close()
        self.path.unlink(missing_ok=True)

    def frame(self, stamp, span=100, hands=None):
        return dict(rgb=np.zeros((480, 640, 3), np.uint8), time=stamp, eye_span=span,
                    faces=1, hands=hands or [], angles=(1, 2, 3), fps=30, size=(640, 480))

    def test_pages_and_responsive_preview(self):
        for size in ("1320x880", "1040x700"):
            self.app.geometry(size)
            for page in self.app.pages:
                self.app.show_page(page)
                self.app.update()
                self.assertTrue(self.app.pages[page].winfo_ismapped())
            self.app.show_page("overview")
            self.app.update()
            self.assertGreater(self.app.preview.winfo_width(), 300)
            self.assertGreater(self.app.preview.winfo_height(), 250)

    def test_settings_roundtrip_and_startup_switch(self):
        self.app.volume_gesture.set(VOLUME_LABELS["fist"])
        self.app.gesture_hands["volume"].set(HAND_LABELS["Both"])
        self.app.motion_vars["volume_steps"].set(3)
        self.app.startup_var.set(True)
        self.assertTrue(self.app.apply_settings())
        self.assertIsNotNone(self.startup.value)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["gestures"]["volume"]["hand"], "Both")
        self.assertEqual(saved["motion"]["volume_steps"], 3)
        self.assertEqual(saved["volume_gesture"], "fist")
        self.app.startup_var.set(False)
        self.assertTrue(self.app.apply_settings())
        self.assertIsNone(self.startup.value)

    def test_privacy_notice_before_camera_and_saved_once(self):
        with patch("eyedesk.app.messagebox.askyesno", return_value=False):
            self.app.start(persist=False)
        self.assertIsNone(self.app.worker)
        with patch("eyedesk.app.messagebox.askyesno", return_value=True) as notice:
            self.assertTrue(self.app.confirm_privacy())
            self.assertTrue(self.app.confirm_privacy())
            notice.assert_called_once()
        self.assertTrue(json.loads(self.path.read_text(encoding="utf-8"))["privacy_notice_accepted"])

    def test_custom_volume_delay_not_remigrated_on_save(self):
        self.app.motion_vars["pinch_hold"].set(.25)
        self.assertTrue(self.app.apply_settings())
        self.assertEqual(self.app.settings["motion"]["pinch_hold"], .25)

    def test_sliders_preserve_default_precision(self):
        for key, value in self.app.settings["motion"].items():
            self.assertAlmostEqual(self.app.motion_vars[key].get(), value, places=5, msg=key)

    def test_startup_does_not_hide_first_use_notice(self):
        with patch.object(self.app, "start") as start, patch.object(self.app, "iconify") as hide:
            self.app.start_at_login()
            start.assert_not_called()
            hide.assert_not_called()

    def test_mirror_does_not_restart_worker_or_retain_gesture(self):
        self.app.on_frame(self.frame(time.monotonic()), time.monotonic())
        self.app.gestures.pending["mute"] = {"Right": 1}
        self.app.mirror.set(False)
        self.app.change_mirror()
        self.assertFalse(self.app.settings["mirror"])
        self.assertEqual(self.app.gestures.pending, {})
        self.assertIsNone(self.app.worker)

    def test_calibration_saved_and_overlay_clears_on_face_loss(self):
        now = time.monotonic()
        self.app.monitor.start_calibration(60)
        self.app.calibration_started = now
        for i in range(80):
            stamp = now + i*.1
            self.app.on_frame(self.frame(stamp, 100 if i < 30 else 150), stamp)
        self.assertEqual(self.app.settings["calibration"]["baseline"], 100)
        self.assertTrue(self.app.monitor.alert)
        self.assertTrue(self.app.overlay.visible)
        self.app.on_frame(self.frame(now+8, None), now+8)
        self.assertFalse(self.app.overlay.visible)
        self.assertFalse(self.app.live.get())

    def test_restore_calibration_only_for_matching_camera_size(self):
        self.app.settings["calibration"] = dict(camera=0, reference=60, baseline=100, size=[640,480])
        stamp = time.monotonic()
        self.app.on_frame(self.frame(stamp), stamp)
        self.assertEqual(self.app.monitor.baseline_px, 100)
        self.assertAlmostEqual(self.app.monitor.estimate, 60)

    def test_audio_disabled_by_default_and_repeats_configured(self):
        now = time.monotonic()
        with patch("eyedesk.app.send_media") as action:
            for i in range(13):
                stamp = now+i*.1
                self.app.on_frame(self.frame(stamp, hands=[Hand("fist", .5, .5, "Right")]), stamp)
            action.assert_not_called()
        self.app.live.set(True)
        self.app.settings["motion"]["volume_steps"] = 3
        self.app.reset_gestures()
        with patch("eyedesk.app.send_media") as action:
            for i in range(10):
                stamp = now+2+i*.1
                self.app.on_frame(self.frame(stamp, hands=[Hand("pinch", .5, .5 if i<5 else .3, "Right")]), stamp)
            self.assertTrue(action.called)
            action.assert_called_with("volume_up", 3)

    def test_overlay_no_focus_no_interception_and_hidden_after_test(self):
        api = self.app.overlay.api
        api.GetForegroundWindow.restype = ctypes.c_void_p
        before = api.GetForegroundWindow()
        self.app.overlay.preview()
        self.app.update()
        self.assertEqual(before, api.GetForegroundWindow())
        style = api.GetWindowLongW(self.app.overlay.hwnd, -20)
        self.assertEqual(style & (0x20 | 0x08000000 | 0x80000), 0x20 | 0x08000000 | 0x80000)
        self.app.overlay.preview_until = 0
        self.app.overlay.refresh()
        self.assertFalse(self.app.overlay.visible)
