"""Η κάμερα και τα μοντέλα τρέχουν σε ξεχωριστή διεργασία από το παράθυρο.

Γιατί process αντί για thread: ορισμένοι USB drivers κολλάνε μέσα στο read().
Έτσι το Stop μπορεί να τερματίσει τον worker χωρίς να παγώσει το περιβάλλον.
"""
import math
import queue
import time

from .models import load_model_buffers
from .logic import classify_hand


HAND_EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6),
              (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16), (13, 17),
              (0, 17), (17, 18), (18, 19), (19, 20)]


def face_metrics(points, matrices, width, height):
    a, b, nose = points[33], points[263], points[1]
    dx, dy = (b.x - a.x) * width, (b.y - a.y) * height
    span = math.hypot(dx, dy)
    # Η προβολή της μύτης στον άξονα των ματιών απορρίπτει έντονο προφίλ.
    offset = (((nose.x - a.x) * width * dx + (nose.y - a.y) * height * dy)
              / max(span * span, 1))
    frontal = span > 12 and 0.20 < offset < 0.80 and abs(dy) < span * 0.30
    inside = all(0.02 < points[i].x < 0.98 and 0.02 < points[i].y < 0.98
                 for i in (10, 152, 234, 454))
    angles = None
    if len(matrices):
        r = matrices[0][:3, :3].copy()
        # Αφαιρούμε την κλίμακα πριν διαβάσουμε γωνίες από τον πίνακα.
        for col in range(3):
            norm = float(sum(r[:, col] ** 2) ** 0.5)
            if norm > 0:
                r[:, col] /= norm
        yaw = math.degrees(math.atan2(-r[2, 0], math.hypot(r[0, 0], r[1, 0])))
        pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
        roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
        angles = (yaw, pitch, roll)
        frontal = frontal and abs(yaw) < 22 and abs(pitch) < 22
    return (span if frontal and inside else None), angles


def offer(channel, message):
    # Κρατάμε πρόσφατα frames. Η συσσώρευση θα έδινε καθυστερημένες εντολές.
    try:
        channel.put_nowait(message)
    except queue.Full:
        try:
            channel.get_nowait()
        except queue.Empty:
            pass
        try:
            channel.put_nowait(message)
        except queue.Full:
            pass


def run_worker(index, channel, stop):
    cap = None
    try:
        # Σε frozen build ένα DLL/import μπορεί να λείπει. Το στέλνουμε στη GUI
        # μέσα από το ίδιο error channel, αντί να χαθεί σε ανύπαρκτη κονσόλα.
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import vision

        buffers = load_model_buffers(lambda text: offer(channel, {"kind": "status", "text": text}))
        common = dict(running_mode=vision.RunningMode.VIDEO)
        hand_options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=buffers["hand_landmarker"]),
            num_hands=2, min_hand_detection_confidence=0.65, **common)
        face_options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=buffers["face_landmarker"]),
            num_faces=2, output_facial_transformation_matrixes=True, **common)
        with vision.HandLandmarker.create_from_options(hand_options) as hands, \
             vision.FaceLandmarker.create_from_options(face_options) as faces:
            if stop.is_set():
                return
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError("Δεν άνοιξε η κάμερα. Κλείσε browser/άλλες εφαρμογές ή δοκίμασε άλλο Camera ID.")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            last_ok = time.monotonic()
            previous = last_ok
            previous_stamp = -1
            fps = 0.0
            while not stop.is_set():
                ok, frame = cap.read()
                captured = time.monotonic()
                if not ok or frame is None:
                    if captured - last_ok > 3:
                        raise RuntimeError("Η κάμερα σταμάτησε να δίνει εικόνα. Έλεγξε το USB και πάτησε ξανά Έναρξη.")
                    time.sleep(0.025)
                    continue
                last_ok = captured
                frame = cv2.flip(frame, 1)  # Καθρέφτης: κίνηση δεξιά = δεξιά στην οθόνη.
                height, width = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                stamp = max(previous_stamp + 1, int(captured * 1000))
                previous_stamp = stamp
                hand_result = hands.detect_for_video(image, stamp)
                face_result = faces.detect_for_video(image, stamp)
                measurements = []
                for points, handedness in zip(hand_result.hand_landmarks, hand_result.handedness):
                    # Χρησιμοποιούμε μόνο confident handedness για να μην αλλάζει χέρι ο έλεγχος.
                    side = handedness[0].category_name
                    if handedness[0].score >= 0.70:
                        measurements.append(classify_hand(points, side, width, height))
                    pixels = [(int(p.x * width), int(p.y * height)) for p in points]
                    for a, b in HAND_EDGES:
                        cv2.line(rgb, pixels[a], pixels[b], (78, 223, 190), 2)
                    for point in pixels:
                        cv2.circle(rgb, point, 3, (247, 199, 88), -1)
                    # Τα ονόματα χεριών εμφανίζονται στη GUI: το mirror δεν καθρεφτίζει γράμματα.
                eye_span, angles = None, None
                count = len(face_result.face_landmarks)
                if count == 1:
                    points = face_result.face_landmarks[0]
                    eye_span, angles = face_metrics(points, face_result.facial_transformation_matrixes, width, height)
                for points in face_result.face_landmarks:
                    for edge in vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS:
                        a, b = points[edge.start], points[edge.end]
                        cv2.line(rgb, (int(a.x * width), int(a.y * height)),
                                 (int(b.x * width), int(b.y * height)), (108, 156, 230), 1)
                now = time.monotonic()
                fps = 0.8 * fps + 0.2 / max(now - previous, 0.001)
                previous = now
                offer(channel, {"kind": "frame", "rgb": rgb, "time": captured,
                                "eye_span": eye_span, "angles": angles, "faces": count,
                                "hands": measurements, "fps": fps, "size": (width, height)})
    except Exception as error:
        offer(channel, {"kind": "error", "text": str(error)})
    finally:
        if cap is not None:
            cap.release()
        # Ο worker δεν περιμένει να καταναλώσει η GUI τα υπόλοιπα numpy frames.
        channel.cancel_join_thread()
