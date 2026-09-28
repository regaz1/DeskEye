"""Το παράθυρο του project. Μόνο το κύριο thread αγγίζει τα Tk widgets.

Ροή: worker → τελευταία εικόνα/σημεία → λογική → προαιρετική εντολή Windows.
Δεν αποθηκεύουμε εικόνες, βίντεο ή τις θέσεις των landmarks στον δίσκο.
"""
import json
import logging
import multiprocessing as multiprocessing
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk, ImageOps

from .actions import send_media
from .logic import DistanceMonitor, GestureRouter, display_hands
from .runtime import DATA, ROOT
from .vision import run_worker
from . import settings as config, startup
from .overlay import Overlay
from .ui import Interface, BG, PANEL, TEXT, TEAL, RED

POSES = {"pinch": "Pinch · ένωση αντίχειρα/δείκτη", "fist": "Γροθιά", "palm": "Ανοιχτή παλάμη",
         "victory": "V · δύο δάχτυλα", "other": "Χέρι / χωρίς εντολή"}
ACTIONS = {"volume_up": "Ένταση +", "volume_down": "Ένταση −", "mute": "Σίγαση / επαναφορά",
           "play_pause": "Αναπαραγωγή / παύση", "next": "Επόμενο κομμάτι", "previous": "Προηγούμενο κομμάτι"}


class App(tk.Tk, Interface):
    def __init__(self, auto_start=False, config_path=None, startup_api=None):
        super().__init__()
        self.title("DeskEye 0.3")
        try:
            self.iconbitmap(str(ROOT / "assets" / "deskeye.ico"))
        except tk.TclError:
            pass
        self.configure(bg=BG)
        width = min(1320, self.winfo_screenwidth() - 60)
        height = min(880, self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}")
        self.minsize(min(1040, width), min(700, height))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.context = multiprocessing.get_context("spawn")
        self.worker = None
        self.channel = None
        self.stop_event = None
        self.stopping = False
        self.started = None
        self.last_frame = None
        self.last_sample = None
        self.last_size = None
        self.calibration_started = None
        self.last_notice = -100.0
        self.closed = False
        self.monitor = DistanceMonitor()
        self.startup_api = startup_api or startup
        self.config_path = Path(config_path) if config_path else DATA / "settings.json"
        self.settings = config.defaults()
        try:
            self.settings = config.validate(json.loads(self.config_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            pass
        try:
            self.settings["startup"] = bool(self.startup_api.current_command())
        except OSError:
            self.settings["startup"] = False
        self.gestures = GestureRouter(self.settings)
        self.live = tk.BooleanVar(value=False)
        self.paused = tk.BooleanVar(value=False)
        self.camera = tk.StringVar(value=str(self.settings["camera"]))
        self.reference = tk.StringVar(value=str(self.settings["reference"]))
        self.threshold = tk.StringVar(value=str(self.settings["threshold"]))
        self.alert_delay = tk.StringVar(value=str(self.settings["alert_delay"]))
        self.sound = tk.BooleanVar(value=self.settings["sound"])
        self.mirror = tk.BooleanVar(value=self.settings["mirror"])
        self.overlay_enabled = tk.BooleanVar(value=self.settings["overlay_enabled"])
        self.startup_var = tk.BooleanVar(value=self.settings["startup"])
        self.volume_gesture = tk.StringVar(value=config.VOLUME_LABELS[self.settings["volume_gesture"]])
        self.motion_vars = {key: tk.DoubleVar(value=value) for key, value in self.settings["motion"].items()}
        self.gesture_enabled = {key: tk.BooleanVar(value=rule["enabled"]) for key, rule in self.settings["gestures"].items()}
        self.gesture_hands = {key: tk.StringVar(value=config.HAND_LABELS[rule["hand"]]) for key, rule in self.settings["gestures"].items()}
        self.overlay = Overlay(self)
        self.build_ui()
        self.bind("<Escape>", self.emergency_pause)
        self.after(35, self.poll)
        if auto_start:
            self.after(700, self.start_at_login)

    def start_at_login(self):
        # Πρώτη χρήση: η ενημέρωση πρέπει να διαβαστεί με το παράθυρο ορατό.
        if not self.settings["privacy_notice_accepted"]:
            self.status.configure(text="Πάτησε Έναρξη για την πρώτη ρύθμιση της παρακολούθησης.")
            return
        self.start(persist=False)
        if self.worker is not None:
            self.iconify()

    def save_settings(self):
        # Η βαθμονόμηση είναι αριθμητικά δεδομένα, όχι αποθήκευση εικόνας προσώπου.
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.config_path)

    def apply_settings(self):
        reverse = {label: key for key, label in config.HAND_LABELS.items()}
        try:
            volume_modes = {label: key for key, label in config.VOLUME_LABELS.items()}
            values = config.validate(dict(schema=3, camera=self.camera.get(), reference=self.reference.get(),
                threshold=self.threshold.get(), sound=self.sound.get(), mirror=self.mirror.get(),
                alert_delay=self.alert_delay.get(), overlay_enabled=self.overlay_enabled.get(),
                startup=self.startup_var.get(), calibration=self.settings.get("calibration"),
                volume_gesture=volume_modes[self.volume_gesture.get()],
                privacy_notice_accepted=self.settings["privacy_notice_accepted"],
                motion={key: var.get() for key, var in self.motion_vars.items()},
                gestures={key: dict(enabled=self.gesture_enabled[key].get(),
                    hand=reverse[self.gesture_hands[key].get()]) for key in config.GROUPS}))
        except (ValueError, TypeError, KeyError, tk.TclError) as error:
            messagebox.showerror("Ρυθμίσεις", str(error), parent=self)
            return False
        if self.worker is not None and values["camera"] != self.settings["camera"]:
            messagebox.showinfo("Κάμερα", "Πάτησε Διακοπή πριν αλλάξεις Camera ID.", parent=self)
            return False
        if values["reference"] != self.settings["reference"] or values["camera"] != self.settings["camera"]:
            self.monitor = DistanceMonitor()
            self.calibration_started = None
            values["calibration"] = None
        try:
            # Γράφεται μόνο η δική μας τιμή στο Run key, όταν αλλάζει η επιλογή.
            self.startup_api.set_enabled(values["startup"])
        except (OSError, ValueError) as error:
            self.status.configure(text=f"Δεν άλλαξε η εκκίνηση με Windows: {error}")
            return False
        self.settings = values
        self.gestures = GestureRouter(values)
        self.monitor.clear_live()
        self.overlay.set_alert(False)
        try:
            self.save_settings()
            self.status.configure(text="Αποθηκεύτηκαν · οι νέες ρυθμίσεις εφαρμόζονται τώρα.")
        except OSError:
            self.status.configure(text="Οι ρυθμίσεις ισχύουν τώρα, αλλά δεν αποθηκεύτηκαν στον δίσκο.")
        return True

    def set_preset(self, name):
        for key, value in config.PRESETS[name].items():
            self.motion_vars[key].set(value)
        self.status.configure(text=f"Προφίλ {name} · πάτησε Αποθήκευση αλλαγών για εφαρμογή.")

    def change_mirror(self):
        self.settings["mirror"] = self.mirror.get()
        self.gestures.reset()  # Μια αλλαγή mirror δεν πρέπει να θεωρηθεί swipe.
        self.status.configure(text="Το mirror άλλαξε · αποθήκευσε για την επόμενη εκκίνηση.")

    def reset_gestures(self):
        self.gestures.reset()
        self.mode.configure(text="PAUSE" if self.paused.get() else
                            ("ΕΝΤΟΛΕΣ ΕΝΕΡΓΕΣ" if self.live.get() else "ΔΟΚΙΜΗ ΕΝΤΟΛΩΝ"),
                            fg=RED if self.live.get() and not self.paused.get() else TEAL)

    def emergency_pause(self, _event=None):
        self.live.set(False)
        self.paused.set(True)
        self.reset_gestures()
        self.status.configure(text="Οι εντολές χειρονομιών σταμάτησαν. Η παρακολούθηση απόστασης συνεχίζεται.")

    def start(self, persist=True):
        if self.worker is not None or (persist and not self.apply_settings()):
            return
        if not self.confirm_privacy():
            return
        self.monitor = DistanceMonitor()  # Επαναφορά αποθηκευμένης βαθμονόμησης μόνο μετά το πρώτο frame.
        self.gestures.reset()
        self.live.set(False)
        self.reset_gestures()
        self.last_frame = None
        self.last_sample = None
        self.last_size = None
        self.started = time.monotonic()
        try:
            self.channel = self.context.Queue(maxsize=2)
            self.stop_event = self.context.Event()
            self.worker = self.context.Process(target=run_worker,
                                               args=(self.settings["camera"], self.channel, self.stop_event), daemon=True)
            self.worker.start()
        except (OSError, RuntimeError) as error:
            # Ακόμη και αν τα Windows αρνηθούν τη δημιουργία worker, η GUI μένει ζωντανή.
            if self.channel is not None:
                self.channel.close()
                self.channel.cancel_join_thread()
                self.channel = None
            self.worker = None
            self.status.configure(text=f"Δεν ξεκίνησε ο worker: {error}")
            return
        self.stopping = False
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.configure(text="Φόρτωση μοντέλων και άνοιγμα κάμερας…")

    def stop(self, reason="Η κάμερα έκλεισε."):
        if self.worker is None or self.stopping:
            return
        self.stopping = True
        self.stop_event.set()
        self.live.set(False)
        self.reset_gestures()
        self.monitor = DistanceMonitor()
        self.calibration_started = None
        self.last_frame = None
        self.stop_button.configure(state="disabled")
        self.status.configure(text=reason)
        self.preview.configure(image="", text="Η κάμερα είναι κλειστή")
        self.preview.image = None
        self.banner.configure(text="Χωρίς μέτρηση απόστασης", bg=PANEL, fg=TEXT)
        self.tracking.configure(text="Πρόσωπο: —    Χέρια: —    FPS: —")
        self.pose_label.configure(text="Κεφάλι: —")
        self.distance_value.configure(text="— cm")
        self.gesture_label.configure(text="Χειρονομία: —")
        self.overlay.hide()
        self.after(50, lambda: self.finish_stop(time.monotonic() + 1.2))

    def finish_stop(self, deadline):
        if self.closed or self.worker is None:
            return
        if self.worker.is_alive() and time.monotonic() < deadline:
            self.after(80, lambda: self.finish_stop(deadline))
            return
        if self.worker.is_alive():
            self.worker.terminate()
        self.worker.join(timeout=0.25)
        if self.worker.is_alive():
            self.after(80, lambda: self.finish_stop(deadline))
            return
        self.worker.close()
        self.channel.close()
        self.channel.cancel_join_thread()
        self.worker = None
        self.channel = None
        self.stopping = False
        self.start_button.configure(state="normal")

    def calibrate(self):
        if self.worker is None or self.stopping or self.last_frame is None:
            messagebox.showinfo("Βαθμονόμηση", "Ξεκίνα πρώτα την κάμερα.", parent=self)
            return
        if not self.apply_settings():
            return
        self.monitor.start_calibration(self.settings["reference"])
        self.settings["calibration"] = None
        try:
            self.save_settings()  # Δεν επαναφέρουμε παλιά βαθμονόμηση αν η νέα διακοπεί.
        except OSError:
            pass
        self.overlay.hide()
        self.calibration_started = time.monotonic()
        self.live.set(False)
        self.reset_gestures()
        self.status.configure(text="Βαθμονόμηση: κοίτα ευθεία για 30 σταθερά frames. Οι εντολές είναι σε δοκιμή.")

    def poll(self):
        if self.closed:
            return
        now = time.monotonic()
        if self.channel is not None and not self.stopping:
            latest = None
            try:
                while True:
                    message = self.channel.get_nowait()
                    if message["kind"] == "error":
                        logging.error("Tracking worker: %s", message["text"])
                        self.stop("Σφάλμα: " + message["text"])
                        latest = None
                        break
                    if message["kind"] == "status":
                        self.status.configure(text=message["text"])
                    else:
                        latest = message
            except queue.Empty:
                pass
            if latest is not None and not self.stopping:
                # Απορρίπτω stale αποτελέσματα αντί να στείλω καθυστερημένο gesture.
                if now - latest["time"] <= 1.0:
                    self.on_frame(latest, now)
            if self.worker is not None and not self.stopping:
                if not self.worker.is_alive():
                    logging.error("Tracking worker exited unexpectedly: %s", self.worker.exitcode)
                    self.stop("Η παρακολούθηση σταμάτησε. Δοκίμασε ξανά ή έλεγξε το αρχείο deskeye.log στον φάκελο ρυθμίσεων.")
                elif self.last_frame is None and now - self.started > 75:
                    self.stop("Η κάμερα ή τα μοντέλα δεν απάντησαν. Έλεγξε το USB και δοκίμασε ξανά.")
                elif self.last_frame is not None and now - self.last_frame > 3:
                    self.stop("Χάθηκε η εικόνα. Οι εντολές απενεργοποιήθηκαν.")
        self.after(35, self.poll)

    def confirm_privacy(self):
        """Ενημέρωση μία φορά πριν φορτωθούν τα μοντέλα ή ανοίξει η κάμερα."""
        if self.settings["privacy_notice_accepted"]:
            return True
        accepted = messagebox.askyesno("DeskEye · Πριν ξεκινήσεις",
            "Η εικόνα επεξεργάζεται στον υπολογιστή σου και το DeskEye δεν καταγράφει βίντεο.\n\n"
            "Σύμφωνα με την Google, τα MediaPipe Tasks στέλνουν στην Google μετρικές απόδοσης "
            "και χρήσης, χωρίς την εικόνα της κάμερας. Περισσότερα στη σελίδα Σύστημα και στο README.\n\n"
            "Συμφωνείς να χρησιμοποιήσεις την παρακολούθηση με αυτούς τους όρους;",
            parent=self)
        if accepted:
            self.settings["privacy_notice_accepted"] = True
            try:
                self.save_settings()
            except OSError:
                pass  # Αν δεν αποθηκευτεί, η ενημέρωση θα εμφανιστεί ξανά.
        else:
            self.status.configure(text="Η κάμερα παρέμεινε κλειστή.")
        return accepted

    def on_frame(self, data, now):
        if self.last_sample is not None and data["time"] - self.last_sample > 0.5:
            self.monitor.clear_live()
            if self.monitor.collecting:
                self.monitor.samples.clear()
            self.gestures.reset()
        self.last_sample = data["time"]
        first = self.last_frame is None
        self.last_frame = now
        if self.last_size is not None and self.last_size != data["size"]:
            self.monitor = DistanceMonitor()
        self.last_size = data["size"]
        if first:
            self.status.configure(text="Κάμερα ενεργή · κάνε βαθμονόμηση και δοκίμασε τις χειρονομίες.")
        if first:
            saved = self.settings.get("calibration")
            if saved and saved["camera"] == self.settings["camera"] and saved["reference"] == self.settings["reference"] and tuple(saved["size"]) == tuple(data["size"]):
                self.monitor.baseline_px = saved["baseline"]
                self.monitor.reference_cm = saved["reference"]
                self.status.configure(text="Επαναφορά βαθμονόμησης · επανάλαβέ την αν άλλαξε θέση η κάμερα.")
        image = Image.fromarray(data["rgb"])
        if not self.settings["mirror"]:
            image = ImageOps.mirror(image)
        image.thumbnail((max(100, self.preview.winfo_width()), max(100, self.preview.winfo_height())), Image.Resampling.BILINEAR)
        photo = ImageTk.PhotoImage(image)
        self.preview.configure(image=photo, text="")
        self.preview.image = photo
        was_collecting = self.monitor.collecting
        distance = self.monitor.update(data["eye_span"], data["time"], self.settings["threshold"], self.settings["alert_delay"])
        if was_collecting and not self.monitor.collecting:
            self.calibration_started = None
            self.settings["calibration"] = dict(camera=self.settings["camera"], reference=self.monitor.reference_cm,
                baseline=self.monitor.baseline_px, size=list(data["size"]))
            try:
                self.save_settings()
                self.status.configure(text="Η βαθμονόμηση αποθηκεύτηκε. Επανάλαβέ την αν μετακινήσεις την κάμερα.")
            except OSError:
                self.status.configure(text="Η βαθμονόμηση ισχύει μόνο σε αυτή τη συνεδρία.")
        if self.monitor.collecting and now - self.calibration_started > 20:
            self.monitor.collecting = False
            self.monitor.samples.clear()
            self.status.configure(text="Η βαθμονόμηση δεν σταθεροποιήθηκε. Κοίτα ευθεία, έλεγξε τον φωτισμό και ξαναδοκίμασε.")
        if self.monitor.collecting:
            banner = f"Βαθμονόμηση… {len(self.monitor.samples)}/30 σταθερά frames"
        elif self.monitor.alert:
            banner = f"Πολύ κοντά · περίπου {distance:.0f} cm — απομακρύνσου λίγο"
            if now - self.last_notice >= 20:
                self.last_notice = now
                self.play_warning()
        elif distance is not None:
            banner = f"Εκτίμηση απόστασης ≈ {distance:.0f} cm  ·  όριο {self.settings['threshold']:.0f} cm"
        elif data["faces"] == 0:
            banner = "Δεν εντοπίζεται πρόσωπο"
        elif data["faces"] > 1:
            banner = "Περισσότερα από ένα πρόσωπα · η μέτρηση έχει παύσει"
        elif self.monitor.baseline_px is None:
            banner = "Πάτησε Βαθμονόμηση απόστασης για να ξεκινήσει η μέτρηση"
        else:
            banner = "Κοίτα ευθεία με όλο το πρόσωπο μέσα στην εικόνα"
        self.banner.configure(text=banner, bg="#702f37" if self.monitor.alert else PANEL, fg=TEXT)
        self.overlay.set_alert(self.monitor.alert and self.settings["overlay_enabled"])
        self.distance_value.configure(text=f"≈ {distance:.0f} cm" if distance is not None else "— cm",
                                      fg=RED if self.monitor.alert else TEXT)
        self.tracking.configure(text=f"Πρόσωπα: {data['faces']}    Χέρια: {len(data['hands'])}    FPS: {data['fps']:.1f}    {data['size'][0]}×{data['size'][1]}")
        if data["angles"]:
            yaw, pitch, roll = data["angles"]
            self.pose_label.configure(text=f"Κεφάλι · yaw {yaw:+.0f}°   pitch {pitch:+.0f}°   roll {roll:+.0f}° (εκτίμηση)")
        else:
            self.pose_label.configure(text="Κεφάλι: —")
        hands = display_hands(data["hands"], self.settings["mirror"])
        descriptions = [f"{config.HAND_LABELS.get(h.side, h.side)}: {POSES[h.pose]}" for h in hands]
        self.gesture_label.configure(text="\n".join(descriptions) if descriptions else "Χέρια: —")
        actions = self.gestures.update(hands, data["time"], not self.paused.get() and not self.monitor.collecting)
        for action in actions:
            prefix = "Δοκιμή" if not self.live.get() else "Εντολή"
            self.action_label.configure(text=f"{prefix}: {ACTIONS[action]}  ·  {time.strftime('%H:%M:%S')}")
            if self.live.get():
                try:
                    send_media(action, self.settings["motion"]["volume_steps"])
                except Exception as error:
                    self.live.set(False)
                    self.reset_gestures()
                    self.status.configure(text=f"Οι εντολές απενεργοποιήθηκαν: {error}")

    def play_warning(self):
        if self.settings["sound"]:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)

    def close(self):
        self.closed = True
        self.live.set(False)
        if self.worker is not None:
            self.stop_event.set()
            self.worker.join(timeout=0.4)
            if self.worker.is_alive():
                self.worker.terminate()
                self.worker.join(timeout=0.5)
            if not self.worker.is_alive():
                self.worker.close()
            self.channel.close()
            self.channel.cancel_join_thread()
        self.overlay.close()
        # Ακυρώνουμε callbacks πριν καταστραφούν οι Tcl εντολές των widgets.
        for timer in self.tk.call("after", "info"):
            self.after_cancel(timer)
        self.destroy()
