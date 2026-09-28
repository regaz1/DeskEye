"""Εντολές πολυμέσων στα Windows, χωρίς εξάρτηση από εξωτερικό πρόγραμμα."""

import ctypes
from ctypes import wintypes
import os


KEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
        "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1}


class KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    # Η union χρειάζεται σωστό μέγεθος ακόμη κι αν στέλνουμε μόνο πλήκτρα.
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyboardInput), ("mi", MouseInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]


def send_media(action, repeats=1):
    if os.name != "nt":
        raise RuntimeError("Οι εντολές ήχου υποστηρίζονται μόνο στα Windows.")
    key = KEYS[action]
    # Επαναλήψεις επιτρέπονται μόνο για ένταση, ποτέ σε toggle τύπου mute.
    repeats = max(1, min(5, int(repeats))) if action.startswith("volume_") else 1
    events = (Input * (2 * repeats))()
    for index in range(2 * repeats):
        flags = 0x0002 if index % 2 else 0
        events[index].type = 1  # INPUT_KEYBOARD: πάτημα, έπειτα απελευθέρωση.
        events[index].data.ki = KeyboardInput(key, 0, flags, 0, 0)
    api = ctypes.WinDLL("user32", use_last_error=True).SendInput
    api.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    api.restype = wintypes.UINT
    if api(len(events), events, ctypes.sizeof(Input)) != len(events):
        raise RuntimeError("Τα Windows δεν δέχτηκαν την εντολή πολυμέσων.")
