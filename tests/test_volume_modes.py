"""Έλεγχοι ασφάλειας/απόκρισης για pinch και κλειστή παλάμη."""
import unittest
from types import SimpleNamespace

from eyedesk.logic import GestureEngine, GestureRouter, Hand, classify_hand
from eyedesk.settings import defaults, validate, LEGACY_VOLUME_DEFAULTS, MOTION_DEFAULTS


class DirectVolumeTests(unittest.TestCase):
    def test_default_uses_initial_movement_after_short_hold(self):
        engine = GestureEngine()
        self.assertIsNone(engine.update(Hand("pinch", .5, .5, "Right"), 0))
        self.assertIsNone(engine.update(Hand("pinch", .5, .47, "Right"), .05))
        # Η κίνηση πριν από το τέλος του hold δεν πετιέται όπως παλιότερα.
        self.assertEqual(engine.update(Hand("pinch", .5, .44, "Right"), .11), "volume_up")

    def test_stationary_hand_does_not_drain_queued_volume(self):
        engine = GestureEngine(dict(smoothing=0))
        engine.update(Hand("pinch", .5, .7, "Right"), 0)
        self.assertEqual(engine.update(Hand("pinch", .5, .3, "Right"), .11), "volume_up")
        for i in range(1, 11):
            self.assertIsNone(engine.update(Hand("pinch", .5, .3, "Right"), .11+i*.1))
        self.assertEqual(engine.update(Hand("pinch", .5, .4, "Right"), 1.3), "volume_down")

    def test_fist_controls_volume_and_never_play_pause(self):
        engine = GestureEngine(dict(smoothing=0), volume_gesture="fist")
        output = [engine.update(Hand("fist", .5, .6-i*.012, "Right"), i*.1) for i in range(25)]
        self.assertIn("volume_up", output)
        self.assertNotIn("play_pause", output)
        self.assertNotIn("mute", output)

    def test_fist_noise_cannot_become_mute_until_neutral_release(self):
        engine = GestureEngine(dict(smoothing=0), volume_gesture="fist")
        for i in range(5):
            engine.update(Hand("fist", .5, .5, "Right"), i*.1)
        noise = [engine.update(Hand("victory", .5, .5, "Right"), .5+i*.1) for i in range(20)]
        self.assertFalse(any(noise))
        for i in range(6):
            engine.update(Hand("palm", .5, .5, "Right"), 2.5+i*.1)
        intentional = [engine.update(Hand("victory", .5, .5, "Right"), 3.1+i*.1) for i in range(15)]
        self.assertEqual(intentional.count("mute"), 1)

    def test_tracking_loss_releases_fist_guard_without_stale_movement(self):
        engine = GestureEngine(dict(smoothing=0), volume_gesture="fist")
        for i in range(5):
            engine.update(Hand("fist", .5, .6, "Right"), i*.1)
        for i in range(6):
            engine.update(None, .5+i*.1)
        self.assertIsNone(engine.update(Hand("fist", .5, .1, "Right"), 1.1))
        self.assertIsNone(engine.update(Hand("fist", .5, .1, "Right"), 1.3))

    def test_first_fist_frame_reserves_pose_before_activation_hold(self):
        engine = GestureEngine(volume_gesture="fist")
        engine.update(Hand("fist", .5, .5, "Right"), 0)
        output = [engine.update(Hand("victory", .5, .5, "Right"), .05+i*.1) for i in range(20)]
        self.assertFalse(any(output))


class FistRoutingTests(unittest.TestCase):
    def config(self, hand="Right"):
        data = defaults()
        data["volume_gesture"] = "fist"
        data["motion"]["smoothing"] = 0
        data["gestures"]["volume"]["hand"] = hand
        data["gestures"]["play_pause"]["hand"] = "Either"
        data["gestures"]["mute"]["hand"] = "Either"
        return data

    def frames(self, router, sides, moving=True, count=20):
        output = []
        for i in range(count):
            y = .7-i*.02 if moving else .5
            output.extend(router.update([Hand("fist", .5, y, side) for side in sides], i*.1))
        return output

    def test_selected_hand_is_reserved_and_other_can_play_pause(self):
        router = GestureRouter(self.config())
        output = self.frames(router, ["Left", "Right"])
        self.assertIn("volume_up", output)
        self.assertEqual(output.count("play_pause"), 1)
        self.assertNotIn("mute", output)

    def test_either_reserves_both_hands(self):
        output = self.frames(GestureRouter(self.config("Either")), ["Left", "Right"])
        self.assertIn("volume_up", output)
        self.assertNotIn("play_pause", output)

    def test_both_requires_matching_movement_and_reserves_missing_partner(self):
        self.assertEqual(self.frames(GestureRouter(self.config("Both")), ["Right"]), [])
        output = self.frames(GestureRouter(self.config("Both")), ["Left", "Right"])
        self.assertIn("volume_up", output)
        self.assertNotIn("play_pause", output)

    def test_disabled_volume_releases_fist_for_play_pause(self):
        data = self.config()
        data["gestures"]["volume"]["enabled"] = False
        output = self.frames(GestureRouter(data), ["Right"], moving=False)
        self.assertEqual(output, ["play_pause"])

    def test_pinch_is_inert_when_fist_method_is_selected(self):
        router = GestureRouter(self.config())
        output = []
        for i in range(15):
            output.extend(router.update([Hand("pinch", .5, .7-i*.03, "Right")], i*.1))
        self.assertEqual(output, [])


class VolumeSettingsTests(unittest.TestCase):
    def test_round_trip_and_invalid_method(self):
        data = defaults()
        data["volume_gesture"] = "fist"
        self.assertEqual(validate(data), data)
        for invalid in ("palm", None, [], 42):
            with self.assertRaises(ValueError):
                validate(dict(volume_gesture=invalid))

    def test_legacy_defaults_upgrade_but_custom_values_are_preserved(self):
        upgraded = validate(dict(schema=2, motion=LEGACY_VOLUME_DEFAULTS))
        self.assertEqual(upgraded["schema"], 3)
        self.assertEqual(upgraded["volume_gesture"], "pinch")
        for key in LEGACY_VOLUME_DEFAULTS:
            self.assertEqual(upgraded["motion"][key], MOTION_DEFAULTS[key])
        customized = validate(dict(schema=2, motion=dict(pinch_hold=.55, pinch_step=.045,
                                volume_interval=.2, volume_steps=4, smoothing=.2)))
        self.assertEqual(customized["motion"]["pinch_hold"], .55)
        self.assertEqual(customized["motion"]["volume_steps"], 4)

    def test_new_schema_preserves_deliberate_legacy_values(self):
        data = validate(dict(schema=3, motion=LEGACY_VOLUME_DEFAULTS))
        for key, value in LEGACY_VOLUME_DEFAULTS.items():
            self.assertEqual(data["motion"][key], value)


class HandClassificationTests(unittest.TestCase):
    def points(self):
        points = [SimpleNamespace(x=.5, y=.7) for _ in range(21)]
        points[0] = SimpleNamespace(x=.5, y=.9)
        for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
            points[mcp] = SimpleNamespace(x=.5, y=.65)
            points[pip] = SimpleNamespace(x=.5, y=.55)
            points[tip] = SimpleNamespace(x=.5, y=.72)
        return points

    def test_fist_tracks_palm_center(self):
        points = self.points()
        hand = classify_hand(points, "Right")
        self.assertEqual(hand.pose, "fist")
        self.assertEqual(hand.y, points[9].y)

    def test_curled_index_and_middle_do_not_make_false_victory(self):
        points = self.points()
        for mcp, pip, tip in ((5, 6, 8), (9, 10, 12)):
            points[mcp] = SimpleNamespace(x=.5, y=.65)
            points[pip] = SimpleNamespace(x=.4, y=.7)
            points[tip] = SimpleNamespace(x=.28, y=.5)
        self.assertEqual(classify_hand(points, "Right").pose, "fist")

    def test_straight_index_and_middle_still_make_victory(self):
        points = self.points()
        for mcp, pip, tip in ((5, 6, 8), (9, 10, 12)):
            points[mcp] = SimpleNamespace(x=.45, y=.68)
            points[pip] = SimpleNamespace(x=.45, y=.5)
            points[tip] = SimpleNamespace(x=.45, y=.27)
        self.assertEqual(classify_hand(points, "Right").pose, "victory")


if __name__ == "__main__":
    unittest.main()
