"""Περιπτώσεις με δύο χέρια, αλλαγή mirror και διαφορετικούς χρόνους."""
import unittest
from unittest.mock import patch, MagicMock
from eyedesk.logic import GestureEngine, GestureRouter, Hand, DistanceMonitor, display_hands
from eyedesk.settings import defaults, validate, PRESETS
from eyedesk.overlay import centered_bounds
from eyedesk import startup


class RoutingTests(unittest.TestCase):
    def router(self, mode="Either", group="mute"):
        settings = defaults()
        settings["motion"]["smoothing"] = 0
        settings["gestures"][group]["hand"] = mode
        return GestureRouter(settings)

    def hold(self, router, sides, start=0, count=15, pose="victory"):
        output = []
        for i in range(count):
            output.extend(router.update([Hand(pose, .5, .5, side) for side in sides], start + i*.1))
        return output

    def test_right_only_ignores_left(self):
        self.assertEqual(self.hold(self.router("Right"), ["Left"]), [])

    def test_left_only_accepts_left(self):
        self.assertEqual(self.hold(self.router("Left"), ["Left"]), ["mute"])

    def test_either_deduplicates_two_hands(self):
        self.assertEqual(self.hold(self.router(), ["Left", "Right"]), ["mute"])

    def test_both_requires_two_hands(self):
        self.assertEqual(self.hold(self.router("Both"), ["Right"]), [])
        self.assertEqual(self.hold(self.router("Both"), ["Left", "Right"]), ["mute"])

    def test_both_accepts_small_timing_difference(self):
        router = self.router("Both")
        output = []
        for i in range(16):
            hands = [Hand("victory", .4, .5, "Right"), Hand("other" if i<2 else "victory", .6, .5, "Left")]
            output.extend(router.update(hands, i*.1))
        self.assertEqual(output, ["mute"])

    def test_both_does_not_pair_with_stale_action(self):
        router = self.router("Both")
        output = []
        for i in range(25):
            hands = [Hand("victory", .4, .5, "Right"), Hand("other" if i<8 else "victory", .6, .5, "Left")]
            output.extend(router.update(hands, i*.1))
        self.assertEqual(output, [])

    def test_each_action_can_use_different_hand(self):
        router = self.router("Left", "mute")
        router.settings["gestures"]["play_pause"]["hand"] = "Right"
        events = []
        for i in range(15):
            events.extend(router.update([Hand("victory", .3, .5, "Left"), Hand("fist", .7, .5, "Right")], i*.1))
        self.assertCountEqual(events, ["mute", "play_pause"])

    def test_opposing_volume_movements_cancel(self):
        router = self.router("Either", "volume")
        self.hold(router, ["Left", "Right"], count=5, pose="pinch")
        actions = router.update([Hand("pinch", .3, .4, "Left"), Hand("pinch", .7, .6, "Right")], .6)
        self.assertEqual(actions, [])

    def test_paused_resets_pending_both(self):
        router = self.router("Both")
        self.hold(router, ["Left", "Right"], count=8)
        router.update([], .8, enabled=False)
        self.assertEqual(self.hold(router, ["Left", "Right"], start=.9, count=3), [])

    def test_mirror_keeps_identity_and_reverses_horizontal_direction(self):
        hand = Hand("palm", .2, .7, "Right")
        changed = display_hands([hand], False)[0]
        self.assertEqual((changed.side, changed.x, changed.y), ("Right", .8, .7))
        self.assertEqual(display_hands([hand], True)[0], hand)

    def test_duplicate_identity_is_ignored(self):
        router = self.router()
        self.assertEqual(self.hold(router, ["Right", "Right"]), [])


class CustomTimingTests(unittest.TestCase):
    def test_custom_hold_changes_activation_time(self):
        engine = GestureEngine(dict(hold_victory=.3))
        events = [engine.update(Hand("victory", .5, .5, "Right"), i*.1) for i in range(6)]
        self.assertEqual(events.count("mute"), 1)
        self.assertIn("mute", events[:5])

    def test_swipe_sensitivity_can_reject_short_movement(self):
        engine = GestureEngine(dict(swipe_distance=.4, smoothing=0))
        events = [engine.update(Hand("palm", .2+i*.07, .5, "Right"), i*.1) for i in range(5)]
        self.assertFalse(any(events))

    def test_long_volume_interval_limits_rate(self):
        engine = GestureEngine(dict(volume_interval=.4, smoothing=0))
        for i in range(5):
            engine.update(Hand("pinch", .5, .5, "Right"), i*.1)
        self.assertEqual(engine.update(Hand("pinch", .5, .4, "Right"), .5), "volume_up")
        self.assertIsNone(engine.update(Hand("pinch", .5, .3, "Right"), .6))

    def test_alert_delay_is_configurable(self):
        monitor = DistanceMonitor()
        monitor.baseline_px = 100
        monitor.reference_cm = 60
        monitor.update(150, 0, delay=.5)
        monitor.update(150, .6, delay=.5)
        self.assertTrue(monitor.alert)


class SettingsTests(unittest.TestCase):
    def test_migrates_old_hand_setting(self):
        result = validate(dict(hand="Left", reference=65, threshold=40))
        self.assertTrue(all(rule["hand"] == "Left" for rule in result["gestures"].values()))
        self.assertEqual(result["schema"], 3)

    def test_presets_and_round_trip(self):
        for preset in PRESETS.values():
            data = defaults()
            data["motion"] = preset
            self.assertEqual(validate(data), data)

    def test_invalid_values_are_rejected(self):
        for data in (dict(camera=1.2), dict(alert_delay=float("nan")), dict(motion=[]),
                     dict(motion=dict(volume_steps=1.5)), dict(gestures=dict(mute=dict(hand="Feet")))):
            with self.assertRaises(ValueError):
                validate(data)

    def test_invalid_calibration_is_discarded(self):
        self.assertIsNone(validate(dict(calibration=dict(size=[1], baseline="bad")))["calibration"])


class StartupTests(unittest.TestCase):
    def test_quotes_paths_and_has_startup_flag(self):
        result = startup.command(executable=r"C:\Program Files\Python\python.exe", root=r"C:\My Project", frozen=False)
        self.assertIn('"C:\\My Project\\main.py"', result)
        self.assertTrue(result.endswith("--startup"))

    def test_frozen_has_no_python_dependency(self):
        result = startup.command(executable=r"C:\Apps\DeskEye.exe", frozen=True)
        self.assertEqual(result, r"C:\Apps\DeskEye.exe --startup")

    def test_long_path_rejected(self):
        with self.assertRaises(ValueError):
            startup.command(executable="C:\\" + "a"*250 + "\\DeskEye.exe", frozen=True)

    def test_registry_enabled_disabled_only_our_value(self):
        import sys
        fake = MagicMock()
        fake.QueryValueEx.side_effect = FileNotFoundError
        key = fake.CreateKeyEx.return_value.__enter__.return_value
        with patch.dict(sys.modules, winreg=fake), patch.object(startup, "current_command", return_value=None), patch.object(startup, "command", return_value='"C:\\Apps\\DeskEye.exe" --startup'):
            startup.set_enabled(True)
            fake.SetValueEx.assert_called_once_with(key, "DeskEye", 0, fake.REG_SZ, '"C:\\Apps\\DeskEye.exe" --startup')
        fake.reset_mock()
        with patch.dict(sys.modules, winreg=fake), patch.object(startup, "current_command", return_value="existing"):
            startup.set_enabled(False)
            fake.DeleteValue.assert_called_once_with(key, "DeskEye")

    def test_no_registry_write_if_unchanged(self):
        import sys
        fake = MagicMock()
        fake.QueryValueEx.side_effect = FileNotFoundError
        with patch.dict(sys.modules, winreg=fake), patch.object(startup, "current_command", return_value=None):
            startup.set_enabled(False)
            fake.CreateKeyEx.assert_not_called()

    def test_rename_migrates_only_legacy_startup_entry(self):
        import sys
        fake = MagicMock()
        key = fake.CreateKeyEx.return_value.__enter__.return_value
        values = {"EyeDesk": "old-app.exe --startup"}
        with patch.dict(sys.modules, winreg=fake), \
             patch.object(startup, "read_command", side_effect=values.get), \
             patch.object(startup, "command", return_value="DeskEye.exe --startup"):
            self.assertEqual(startup.current_command(), values["EyeDesk"])
            startup.set_enabled(True)
        fake.SetValueEx.assert_called_once_with(key, "DeskEye", 0, fake.REG_SZ, "DeskEye.exe --startup")
        fake.DeleteValue.assert_called_once_with(key, "EyeDesk")


class OverlayPlacementTests(unittest.TestCase):
    def test_top_center_and_negative_monitor_origin(self):
        self.assertEqual(centered_bounds(0, 0, 1920), (835, 24))
        self.assertEqual(centered_bounds(-1920, 0, 0), (-1085, 24))
