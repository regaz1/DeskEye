"""Σχήμα ρυθμίσεων, migration από την πρώτη έκδοση και έλεγχος ορίων.

Οι τιμές του JSON είναι δεδομένα: τις ελέγχουμε πριν επηρεάσουν τη μηχανή.
Κάθε χειρονομία έχει δική της επιλογή χεριού, οι χρόνοι είναι σε δευτερόλεπτα.
"""
from copy import deepcopy
from math import isfinite

GROUPS = {
    "volume": ("Ένταση ήχου", "Pinch ή γροθιά + κίνηση πάνω / κάτω", ("volume_up", "volume_down")),
    "play_pause": ("Play / pause", "Κράτησε κλειστή γροθιά", ("play_pause",)),
    "mute": ("Mute / unmute", "Κράτησε το σχήμα V", ("mute",)),
    "next": ("Επόμενο κομμάτι", "Ανοιχτή παλάμη → δεξιά", ("next",)),
    "previous": ("Προηγούμενο κομμάτι", "Ανοιχτή παλάμη → αριστερά", ("previous",)),
}
HAND_LABELS = {"Right": "Δεξί", "Left": "Αριστερό", "Either": "Οποιοδήποτε",
               "Both": "Και τα δύο μαζί"}
VOLUME_LABELS = {"pinch": "Pinch · αντίχειρας και δείκτης", "fist": "Κλειστή παλάμη · γροθιά"}
# Μικρότερο κράτημα/διαδρομή και χαμηλή εξομάλυνση κάνουν την ένταση άμεση.
# Τα παλιά ονόματα pinch_* διατηρούνται στο JSON για συμβατότητα· ισχύουν και για γροθιά.
MOTION_DEFAULTS = dict(hold_fist=.85, hold_victory=.85, cooldown=1.2, pinch_hold=.10,
                       pinch_step=.012, volume_interval=.05, volume_steps=2,
                       smoothing=.035, swipe_distance=.23, swipe_window=.65)
LEGACY_VOLUME_DEFAULTS = dict(pinch_hold=.25, pinch_step=.025, volume_interval=.09,
                              volume_steps=1, smoothing=.08)
# (ελάχιστο, μέγιστο) — περιορίζουμε και τις ακραίες τιμές από χειροκίνητο JSON.
MOTION_LIMITS = {"hold_fist": (.2, 2.5), "hold_victory": (.2, 2.5), "cooldown": (.3, 3),
                 "pinch_hold": (.05, 1), "pinch_step": (.005, .10),
                 "volume_interval": (.03, .4), "volume_steps": (1, 5),
                 "smoothing": (0, .4), "swipe_distance": (.10, .45), "swipe_window": (.3, 1.2)}
PRESETS = {
    "Ήπια": dict(MOTION_DEFAULTS, hold_fist=1.1, hold_victory=1.1, cooldown=1.6,
                 pinch_hold=.4, pinch_step=.035, volume_interval=.15, volume_steps=1, smoothing=.18,
                 swipe_distance=.28, swipe_window=.85),
    "Ισορροπημένη": dict(MOTION_DEFAULTS),
    "Γρήγορη": dict(MOTION_DEFAULTS, hold_fist=.45, hold_victory=.45, cooldown=.6,
                    pinch_hold=.05, pinch_step=.008, volume_interval=.035, smoothing=.02,
                    swipe_distance=.17, swipe_window=.5),
}


def defaults():
    return dict(schema=3, camera=0, reference=60., threshold=45., sound=True, mirror=True,
                alert_delay=2., overlay_enabled=True, startup=False, calibration=None,
                volume_gesture="pinch", privacy_notice_accepted=False,
                motion=deepcopy(MOTION_DEFAULTS),
                gestures={key: dict(enabled=True, hand="Right") for key in GROUPS})


def number(value, low, high, label):
    result = float(value)
    if not isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label}: η τιμή πρέπει να είναι {low:g}–{high:g}.")
    return result


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Οι ρυθμίσεις πρέπει να είναι JSON object.")
    result = defaults()
    camera = number(data.get("camera", 0), 0, 9, "Camera ID")
    if camera != int(camera):
        raise ValueError("Το Camera ID πρέπει να είναι ακέραιος.")
    result["camera"] = int(camera)
    result["reference"] = number(data.get("reference", 60), 25, 150, "Απόσταση βαθμονόμησης")
    result["threshold"] = number(data.get("threshold", 45), 20, 149, "Όριο απόστασης")
    if result["threshold"] >= result["reference"]:
        raise ValueError("Το όριο πρέπει να είναι μικρότερο από την απόσταση βαθμονόμησης.")
    result["alert_delay"] = number(data.get("alert_delay", 2), .3, 8, "Καθυστέρηση ειδοποίησης")
    volume_gesture = data.get("volume_gesture", "pinch")
    if not isinstance(volume_gesture, str) or volume_gesture not in VOLUME_LABELS:
        raise ValueError("Μη έγκυρη χειρονομία έντασης.")
    result["volume_gesture"] = volume_gesture
    for key in ("sound", "mirror", "overlay_enabled", "startup", "privacy_notice_accepted"):
        value = data.get(key, result[key])
        if not isinstance(value, bool):
            raise ValueError(f"Μη έγκυρη επιλογή: {key}")
        result[key] = value
    motion = data.get("motion", {})
    gestures = data.get("gestures", {})
    if not isinstance(motion, dict) or not isinstance(gestures, dict):
        raise ValueError("Οι ρυθμίσεις κίνησης πρέπει να είναι JSON objects.")
    for key, (low, high) in MOTION_LIMITS.items():
        saved = motion.get(key, MOTION_DEFAULTS[key])
        # Αναβαθμίζουμε μόνο τις παλιές εργοστασιακές τιμές, όχι προσωπικές ρυθμίσεις.
        if data.get("schema", 1) in (1, 2) and key in LEGACY_VOLUME_DEFAULTS and saved == LEGACY_VOLUME_DEFAULTS[key]:
            saved = MOTION_DEFAULTS[key]
        value = number(saved, low, high, key)
        if key == "volume_steps":
            if value != int(value):
                raise ValueError("Το βήμα έντασης πρέπει να είναι ακέραιο.")
            value = int(value)
        result["motion"][key] = value
    for group in GROUPS:
        values = gestures.get(group, {})
        if not isinstance(values, dict):
            raise ValueError(f"Μη έγκυρη ρύθμιση χειρονομίας: {group}")
        # Η παλιά καθολική επιλογή χεριού γίνεται προεπιλογή κάθε χειρονομίας.
        hand = values.get("hand", data.get("hand", "Right"))
        enabled = values.get("enabled", True)
        if hand not in HAND_LABELS or not isinstance(enabled, bool):
            raise ValueError(f"Μη έγκυρη ρύθμιση χειρονομίας: {group}")
        result["gestures"][group] = dict(enabled=enabled, hand=hand)
    calibration = data.get("calibration")
    if isinstance(calibration, dict):
        try:
            size = calibration["size"]
            result["calibration"] = dict(
                camera=int(number(calibration["camera"], 0, 9, "Camera ID")),
                reference=number(calibration["reference"], 25, 150, "Απόσταση"),
                baseline=number(calibration["baseline"], 12, 2000, "Pixels"),
                size=[int(number(size[0], 160, 4096, "Πλάτος")),
                      int(number(size[1], 120, 4096, "Ύψος"))])
        except (KeyError, ValueError, TypeError, IndexError):
            result["calibration"] = None
    return result
