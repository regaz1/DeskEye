"""Ελέγχω το Windows event payload χωρίς να στείλω πραγματικά πλήκτρα."""
import ctypes
import os
import unittest
from unittest.mock import patch
from eyedesk.actions import Input, send_media, KEYS


@unittest.skipUnless(os.name == "nt", "Windows ABI test")
class ActionTests(unittest.TestCase):
    def test_media_key_has_matching_release(self):
        for action, key in KEYS.items():
            calls = []
            class SendInputStub:
                def __call__(self, count, events, size):
                    calls.append((count, size, [(e.type, e.data.ki.wVk, e.data.ki.dwFlags) for e in events]))
                    return 2
            class Api:
                SendInput = SendInputStub()
            with patch("eyedesk.actions.ctypes.WinDLL", return_value=Api()):
                send_media(action)
            self.assertEqual(calls, [(2, ctypes.sizeof(Input), [(1, key, 0), (1, key, 2)])])

    def test_blocked_input_reports_error(self):
        class SendInputStub:
            def __call__(self, *args):
                return 0
        class Api:
            SendInput = SendInputStub()
        with patch("eyedesk.actions.ctypes.WinDLL", return_value=Api()):
            with self.assertRaises(RuntimeError):
                send_media("mute")

    def test_volume_strength_repeats_but_toggle_never_repeats(self):
        calls = []
        class SendInputStub:
            def __call__(self, count, events, size):
                calls.append(count)
                return count
        class Api:
            SendInput = SendInputStub()
        with patch("eyedesk.actions.ctypes.WinDLL", return_value=Api()):
            send_media("volume_up", repeats=4)
            send_media("mute", repeats=4)
        self.assertEqual(calls, [8, 2])
