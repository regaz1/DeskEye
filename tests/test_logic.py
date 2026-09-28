"""Regression tests για όσα μπορούν να προκαλέσουν ενοχλητικές εντολές."""
import unittest
from eyedesk.logic import DistanceMonitor, GestureEngine, Hand


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.engine = GestureEngine()

    def frames(self, pose, start, count, x=0.5, y=0.5):
        return [self.engine.update(Hand(pose, x, y, "Right"), start + i * 0.1)
                for i in range(count)]

    def test_fist_fires_once_until_release(self):
        events = self.frames("fist", 0, 60)
        self.assertEqual(events.count("play_pause"), 1)
        self.frames("other", 6, 5)
        self.assertEqual(self.frames("fist", 7, 15).count("play_pause"), 1)

    def test_short_accidental_pose_does_not_fire(self):
        self.assertFalse(any(self.frames("victory", 0, 5)))
        self.frames("other", 0.5, 3)
        self.assertFalse(any(self.frames("victory", 0.8, 5)))

    def test_tracking_gap_cancels_hold(self):
        self.frames("fist", 0, 7)
        self.assertIsNone(self.engine.update(Hand("fist", .5, .5, "Right"), 2))

    def test_disabled_resets_state(self):
        self.frames("fist", 0, 7)
        self.assertIsNone(self.engine.update(Hand("fist", .5, .5, "Right"), .7, False))
        self.assertIsNone(self.engine.update(Hand("fist", .5, .5, "Right"), 1))

    def test_pinch_moves_volume_and_loss_resets_anchor(self):
        self.frames("pinch", 0, 5)
        self.assertEqual(self.engine.update(Hand("pinch", .5, .44, "Right"), .5), "volume_up")
        self.assertEqual(self.engine.update(Hand("pinch", .5, .50, "Right"), .7), "volume_down")
        self.engine.update(None, .8)
        self.assertIsNone(self.engine.update(Hand("pinch", .5, .1, "Right"), .9))

    def test_swipes_follow_mirrored_screen_direction(self):
        for i in range(4):
            result = self.engine.update(Hand("palm", .2 + i * .09, .5, "Right"), i * .1)
        self.assertEqual(result, "next")
        self.assertIsNone(self.engine.update(Hand("palm", .9, .5, "Right"), .4))

    def test_hand_change_does_not_complete_hold(self):
        self.frames("fist", 0, 8)
        self.assertIsNone(self.engine.update(Hand("fist", .5, .5, "Left"), .8))


class DistanceTests(unittest.TestCase):
    def calibrated(self):
        monitor = DistanceMonitor()
        monitor.start_calibration(60)
        for i in range(30):
            monitor.update(100, i * .1)
        self.assertFalse(monitor.collecting)
        return monitor

    def test_inverse_size_distance(self):
        monitor = self.calibrated()
        self.assertAlmostEqual(monitor.update(150, 4), 40)

    def test_alert_delay_and_loss(self):
        monitor = self.calibrated()
        monitor.update(150, 4)
        monitor.update(150, 5.9)
        self.assertFalse(monitor.alert)
        monitor.update(150, 6.1)
        self.assertTrue(monitor.alert)
        monitor.update(None, 6.2)
        self.assertFalse(monitor.alert)
        self.assertIsNone(monitor.estimate)

    def test_brief_approach_does_not_alert(self):
        monitor = self.calibrated()
        for i in range(10):
            monitor.update(150, 4 + i * .1)
        for i in range(30):
            monitor.update(100, 5 + i * .1)
        self.assertFalse(monitor.alert)

    def test_unstable_calibration_and_face_loss(self):
        monitor = DistanceMonitor()
        monitor.start_calibration(60)
        for i in range(40):
            monitor.update(70 if i % 2 else 130, i * .1)
        self.assertTrue(monitor.collecting)
        monitor.update(None, 5)
        self.assertEqual(monitor.samples, [])

    def test_recalibration_clears_previous_baseline(self):
        monitor = self.calibrated()
        monitor.start_calibration(70)
        self.assertIsNone(monitor.baseline_px)
        with self.assertRaises(ValueError):
            monitor.start_calibration(float("nan"))


if __name__ == "__main__":
    unittest.main()
