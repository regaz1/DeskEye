"""Καθαρή λογική, ανεξάρτητη από κάμερα/Windows, για εύκολες δοκιμές.

Σημείωση project: οι χρόνοι είναι monotonic δευτερόλεπτα. Η ώρα συστήματος
μπορεί να αλλάξει και δεν είναι κατάλληλη για holds και cooldowns.
"""

from collections import deque
from dataclasses import dataclass
from math import hypot, isfinite, exp
from statistics import median, pstdev

from .settings import MOTION_DEFAULTS, GROUPS


@dataclass
class Hand:
    pose: str
    x: float
    y: float
    side: str


def classify_hand(points, side, width=640, height=480):
    """Μετατρέπω 21 σημεία σε απλές χειρονομίες, όχι σε γενική νοηματική."""
    def distance(a, b):
        # Τα normalized x/y έχουν διαφορετική κλίμακα: μετράμε σε pixels.
        return hypot((points[a].x - points[b].x) * width,
                     (points[a].y - points[b].y) * height)

    palm = max(distance(0, 9), 1.0)
    def finger_extended(mcp, pip, tip):
        # Η απόσταση από τον καρπό μόνη της μπερδεύει λυγισμένα δάχτυλα με V.
        # Ζητάμε και αρκετά ίσιο δάχτυλο, ελέγχοντας τη γωνία στην άρθρωση PIP.
        ax, ay = (points[mcp].x - points[pip].x) * width, (points[mcp].y - points[pip].y) * height
        bx, by = (points[tip].x - points[pip].x) * width, (points[tip].y - points[pip].y) * height
        lengths = hypot(ax, ay) * hypot(bx, by)
        straight = lengths > 1 and (ax * bx + ay * by) / lengths < -.75
        return straight and distance(tip, 0) > distance(pip, 0) * 1.18

    extended = [finger_extended(mcp, pip, tip)
                for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))]
    # Το pinch απαιτεί τεντωμένα τα υπόλοιπα δάχτυλα ώστε να διαφέρει από γροθιά.
    pinch = distance(4, 8) / palm < 0.30 and sum(extended[1:]) >= 2
    if pinch:
        pose = "pinch"
    elif all(extended):
        pose = "palm"
    elif not any(extended):
        pose = "fist"
    elif extended == [True, True, False, False]:
        pose = "victory"
    else:
        pose = "other"
    # Στη γροθιά ακολουθούμε το σταθερό κέντρο της παλάμης, όχι τις άκρες
    # των δαχτύλων που μετακινούνται όσο την κλείνουμε.
    y = (points[4].y + points[8].y) / 2 if pose == "pinch" else points[9].y
    return Hand(pose, points[9].x, y, side)


class GestureEngine:
    """Hold + release + cooldown αποτρέπουν επαναλήψεις σε κάθε frame."""
    def __init__(self, motion=None, volume_gesture="pinch"):
        self.motion = dict(MOTION_DEFAULTS, **(motion or {}))
        self.volume_gesture = volume_gesture
        self.reset()

    def reset(self):
        self.pose = None
        self.since = 0.0
        self.fired = False
        self.release_since = None
        self.latched = False
        self.last_seen = None
        self.side = None
        self.cooldown = 0.0
        self.anchor_y = None
        self.last_volume = -1e9
        self.history = deque()
        self.smooth = None
        self.volume_guard = False
        self.volume_release_since = None

    def update(self, hand, now, enabled=True):
        if not enabled:
            self.reset()
            return None
        dt = now - self.last_seen if self.last_seen is not None else 0
        if self.last_seen is not None and dt > 0.35:
            # Διακοπή tracking: δεν συνεχίζω το παλιό hold ή την παλιά μετακίνηση.
            self.pose = None
            self.anchor_y = None
            self.history.clear()
            self.smooth = None
            self.volume_guard = False
            self.volume_release_since = None
        self.last_seen = now
        if hand is None:
            self.pose = None
            self.anchor_y = None
            self.history.clear()
            self.smooth = None
            if self.release_since is None:
                self.release_since = now
            elif now - self.release_since >= 0.4:
                self.latched = False
            if self.volume_release_since is None:
                self.volume_release_since = now
            elif now - self.volume_release_since >= .3:
                self.volume_guard = False
            return None
        if hand.side != self.side:
            self.pose = None
            self.anchor_y = None
            self.history.clear()
            self.side = hand.side
            self.smooth = None
            self.volume_guard = False
            self.volume_release_since = None
        # Χρονικά σταθερή εξομάλυνση: ίδια αίσθηση σε διαφορετικά FPS.
        tau = self.motion["smoothing"]
        if self.smooth is not None and tau > 0:
            alpha = 1 - exp(-max(dt, 0) / tau)
            x = self.smooth[0] + alpha * (hand.x - self.smooth[0])
            y = self.smooth[1] + alpha * (hand.y - self.smooth[1])
            hand = Hand(hand.pose, x, y, hand.side)
        self.smooth = (hand.x, hand.y)
        # Μετά από έλεγχο έντασης με γροθιά απαιτείται ουδέτερη στάση/ανοιχτή
        # παλάμη για 0.3 s πριν από άλλη εντολή. Ένα θορυβώδες V δεν κάνει mute.
        if self.volume_guard and hand.pose != self.volume_gesture:
            if hand.pose == "victory":
                self.volume_release_since = None
            elif self.volume_release_since is None:
                self.volume_release_since = now
            elif now - self.volume_release_since >= .3:
                self.volume_guard = False
                self.volume_release_since = None
            self.pose = None
            self.anchor_y = None
            self.history.clear()
            if self.volume_guard:
                return None
        else:
            self.volume_release_since = None
        if hand.pose not in ("fist", "victory"):
            if self.release_since is None:
                self.release_since = now
            elif now - self.release_since >= 0.3:
                self.latched = False
        else:
            self.release_since = None
        if hand.pose != self.pose:
            self.pose = hand.pose
            self.since = now
            self.fired = False
            # Θυμόμαστε τη θέση από το πρώτο frame: η αρχική κίνηση μετράει
            # μόλις ολοκληρωθεί το μικρό κράτημα ενεργοποίησης.
            self.anchor_y = hand.y if hand.pose == self.volume_gesture else None
            self.history.clear()
        if now < self.cooldown:
            self.since = now
            self.anchor_y = None
            self.history.clear()
            return None
        if hand.pose == self.volume_gesture:
            if self.volume_gesture == "fist":
                # Δεσμεύεται από το πρώτο frame, ακόμη πριν τελειώσει το hold.
                self.volume_guard = True
            if now - self.since < self.motion["pinch_hold"]:
                return None
            if self.anchor_y is None:
                self.anchor_y = hand.y
            delta = self.anchor_y - hand.y
            if abs(delta) >= self.motion["pinch_step"] and now - self.last_volume >= self.motion["volume_interval"]:
                # Δεν αφήνουμε ουρά βημάτων: μόλις σταματήσει το χέρι σταματά ο ήχος.
                self.anchor_y = hand.y
                self.last_volume = now
                return "volume_up" if delta > 0 else "volume_down"
        elif hand.pose in ("fist", "victory"):
            hold = self.motion["hold_fist" if hand.pose == "fist" else "hold_victory"]
            if not self.latched and not self.fired and now - self.since >= hold:
                self.fired = self.latched = True
                self.cooldown = now + self.motion["cooldown"]
                return "play_pause" if hand.pose == "fist" else "mute"
        elif hand.pose == "palm":
            self.history.append((now, hand.x))
            while self.history and now - self.history[0][0] > self.motion["swipe_window"]:
                self.history.popleft()
            if len(self.history) >= 3 and now - self.history[0][0] >= 0.18:
                dx = hand.x - self.history[0][1]
                if abs(dx) > self.motion["swipe_distance"]:
                    self.history.clear()
                    self.cooldown = now + self.motion["cooldown"]
                    return "next" if dx > 0 else "previous"
        return None


def display_hands(hands, mirror):
    """Το mirror αλλάζει την κατεύθυνση preview, ποτέ την ταυτότητα Left/Right."""
    return [Hand(h.pose, h.x if mirror else 1 - h.x, h.y, h.side) for h in hands]


class GestureRouter:
    """Ανεξάρτητο tracking ανά χέρι, με κοινή αποφυγή διπλών/αντίθετων εντολών."""
    def __init__(self, settings):
        self.settings = settings
        volume = settings["gestures"]["volume"]
        # Η γροθιά δεσμεύεται μόνο στα χέρια που επιλέχθηκαν για ένταση.
        # Στο Both δεσμεύονται και τα δύο ακόμη κι αν λείπει προσωρινά το ένα.
        self.engines = {
            side: GestureEngine(settings["motion"], settings.get("volume_gesture", "pinch")
                                if volume["enabled"] and volume["hand"] in (side, "Either", "Both") else None)
            for side in ("Left", "Right")}
        self.reset()

    def reset(self):
        for engine in self.engines.values():
            engine.reset()
        self.pending = {}
        self.last_action = {}

    def update(self, hands, now, enabled=True):
        if not enabled:
            self.reset()
            return []
        selected, events = {}, []
        for side, engine in self.engines.items():
            candidates = [h for h in hands if h.side == side]
            selected[side] = candidates[0] if len(candidates) == 1 else None
            event = engine.update(selected[side], now)
            if event:
                events.append((side, event))
        # Σε απώλεια χεριού δεν κρατάμε μισή «διπλή» χειρονομία.
        if any(h is None for h in selected.values()):
            self.pending.clear()
        accepted = set()
        for side, action in events:
            group = next(key for key, (_, _, actions) in GROUPS.items() if action in actions)
            rule = self.settings["gestures"][group]
            if not rule["enabled"]:
                continue
            mode = rule["hand"]
            if mode in ("Left", "Right") and mode != side:
                continue
            if mode == "Both":
                expected = self.settings.get("volume_gesture", "pinch") if group == "volume" else {"play_pause": "fist", "mute": "victory"}.get(group, "palm")
                if any(h is None or h.pose != expected for h in selected.values()):
                    self.pending.pop(action, None)
                    continue
                pair = self.pending.setdefault(action, {})
                pair[side] = now
                other = "Left" if side == "Right" else "Right"
                if other not in pair or now - pair[other] > .35:
                    continue
                self.pending.pop(action, None)
            accepted.add(action)
        # Αν τα χέρια διαφωνούν, δεν αλλάζουμε τον ήχο μπρος-πίσω.
        for a, b in (("volume_up", "volume_down"), ("next", "previous")):
            if a in accepted and b in accepted:
                accepted.difference_update((a, b))
        output = []
        for action in sorted(accepted):
            family = "volume" if action.startswith("volume_") else ("track" if action in ("next", "previous") else action)
            delay = self.settings["motion"]["volume_interval" if family == "volume" else "cooldown"]
            if now - self.last_action.get(family, -1e9) >= delay:
                output.append(action)
                self.last_action[family] = now
        return output


class DistanceMonitor:
    """Μονόφθαλμη εκτίμηση: απόσταση ∝ 1 / μέγεθος προσώπου στην εικόνα."""
    def __init__(self):
        self.baseline_px = None
        self.reference_cm = 60.0
        self.samples = []
        self.collecting = False
        self.estimate = None
        self.near_since = None
        self.alert = False

    def clear_live(self):
        self.estimate = None
        self.near_since = None
        self.alert = False

    def start_calibration(self, cm):
        if not isfinite(cm) or not 25 <= cm <= 150:
            raise ValueError("Η απόσταση βαθμονόμησης πρέπει να είναι 25–150 cm.")
        self.reference_cm = cm
        self.baseline_px = None
        self.samples = []
        self.collecting = True
        self.clear_live()

    def update(self, eye_span, now, threshold=45.0, delay=2.0):
        if eye_span is None or not isfinite(eye_span) or eye_span < 12:
            self.clear_live()
            if self.collecting:
                self.samples.clear()
            return None
        if self.collecting:
            self.samples.append(eye_span)
            self.samples = self.samples[-30:]
            if len(self.samples) == 30:
                center = median(self.samples)
                if pstdev(self.samples) / center < 0.055:
                    self.baseline_px = center
                    self.collecting = False
            return None
        if self.baseline_px is None:
            return None
        raw = self.reference_cm * self.baseline_px / eye_span
        if not 15 <= raw <= 250:
            self.clear_live()
            return None
        # Εξομάλυνση για να μη χορεύει η ένδειξη με κάθε pixel.
        self.estimate = raw if self.estimate is None else self.estimate * 0.75 + raw * 0.25
        if self.estimate < threshold:
            if self.near_since is None:
                self.near_since = now
            self.alert = now - self.near_since >= delay
        elif self.estimate > threshold + 4:
            self.near_since = None
            self.alert = False
        elif not self.alert:
            # Η πρώτη ειδοποίηση απαιτεί συνεχόμενα 2 s κάτω από το όριο.
            self.near_since = None
        return self.estimate
