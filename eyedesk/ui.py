"""Εμφάνιση χωρισμένη από τη λογική: το layout μπορεί να αλλάξει χωρίς tracking.

Κάθε καρτέλα διατηρεί τα widgets της. Έτσι η κάμερα συνεχίζει να δουλεύει όταν
ο χρήστης αλλάζει σελίδα και οι μη αποθηκευμένες ρυθμίσεις δεν χάνονται.
"""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from .runtime import ROOT
from .settings import GROUPS, HAND_LABELS, VOLUME_LABELS, MOTION_LIMITS, PRESETS

# Η παλέτα ακολουθεί το μέταλλο και τους σκούρους φακούς του λογοτύπου.
BG = "#191918"
NAV = "#131312"
PANEL = "#222220"
SOFT = "#2d2c29"
LINE = "#44423e"
TEXT = "#f0efeb"
MUTED = "#b1aea6"
ACCENT = "#c9c1b2"
TEAL = ACCENT  # Το παλιό όνομα παραμένει για τα imports της εφαρμογής.
RED = "#f07878"


class ScrollPanel(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, width=1)
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        item = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(item, width=e.width))


class Interface:
    def label(self, parent, text, size=11, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def check(self, parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
                              bg=parent.cget("bg"), fg=TEXT, selectcolor=SOFT,
                              activebackground=parent.cget("bg"), activeforeground=TEAL,
                              font=("Segoe UI", 10), anchor="w", cursor="hand2")

    def card(self, parent, title, subtitle=None):
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=0)
        outer.pack(fill="x", pady=(0, 12), padx=(0, 6))
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        if title:
            self.label(inner, title, 13, TEXT, True).pack(anchor="w")
        if subtitle:
            self.label(inner, subtitle, 10, MUTED, justify="left", wraplength=680).pack(anchor="w", pady=(4, 12))
        return inner

    def field(self, parent, title, variable, width=12):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=6)
        self.label(row, title, 10, MUTED).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=width, justify="right").pack(side="right")

    def slider(self, parent, title, key, help_text=None):
        low, high = MOTION_LIMITS[key]
        var = self.motion_vars[key]
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(8, 0))
        self.label(row, title, 10, TEXT).pack(side="left")
        value = self.label(row, "", 10, TEAL, True)
        value.pack(side="right")
        def update(*_):
            number = var.get()
            if key in ("pinch_step", "swipe_distance"):
                value.configure(text=f"{number * 100:.1f}%")
            elif key == "volume_steps":
                value.configure(text=f"×{round(number)}")
            else:
                value.configure(text=f"{number:.3f}".rstrip("0").rstrip(".") + " s")
        var.trace_add("write", update)
        update()
        # Χιλιοστά: το widget δεν στρογγυλοποιεί την προεπιλογή 0.035 σε 0.04.
        resolution = 1 if key == "volume_steps" else .001
        tk.Scale(parent, from_=low, to=high, resolution=resolution, variable=var,
                 orient="horizontal", showvalue=False, bd=0, highlightthickness=0,
                 bg=parent.cget("bg"), troughcolor=SOFT, activebackground=TEAL,
                 fg=TEAL, sliderlength=18, width=8).pack(fill="x", pady=(4, 0))
        if help_text:
            self.label(parent, help_text, 9, MUTED, wraplength=690, justify="left").pack(anchor="w", pady=(2, 3))

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(13, 10),
                        background=SOFT, foreground=TEXT, borderwidth=0, focuscolor=TEAL)
        style.map("TButton", background=[("active", LINE), ("disabled", PANEL)],
                  foreground=[("disabled", "#77756f")])
        style.configure("Accent.TButton", background=ACCENT, foreground=NAV)
        style.map("Accent.TButton", background=[("active", "#e0d9cc"), ("disabled", SOFT)],
                  foreground=[("disabled", MUTED)])
        style.configure("TEntry", fieldbackground=SOFT, foreground=TEXT, insertcolor=TEXT, padding=7, bordercolor=LINE)
        style.configure("TCombobox", fieldbackground=SOFT, background=SOFT, foreground=TEXT,
                        arrowcolor=TEAL, padding=7, bordercolor=LINE)
        style.map("TCombobox", fieldbackground=[("readonly", SOFT)], foreground=[("readonly", TEXT)], selectbackground=[("readonly", SOFT)])
        self.option_add("*TCombobox*Listbox.background", SOFT)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        style.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, borderwidth=0, arrowsize=12)
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)
        nav = tk.Frame(shell, bg=NAV, width=178)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        # Κρατάμε αναφορά στο PhotoImage, αλλιώς το Tk θα το αφαιρέσει από τη μνήμη.
        try:
            with Image.open(ROOT / "assets" / "logo.png") as source:
                logo = source.convert("RGBA")
                logo.thumbnail((76, 76), Image.Resampling.LANCZOS)
            self.nav_logo = ImageTk.PhotoImage(logo, master=self)
            tk.Label(nav, image=self.nav_logo, bg=NAV, bd=0).pack(anchor="w", padx=20, pady=(24, 10))
        except (OSError, tk.TclError):
            # Η εφαρμογή παραμένει λειτουργική αν λείπει το προαιρετικό γραφικό.
            tk.Frame(nav, bg=ACCENT, width=34, height=3).pack(anchor="w", padx=22, pady=(34, 18))
        self.label(nav, "DeskEye", 21, TEXT, True).pack(anchor="w", padx=22)
        self.label(nav, "CAMERA CONTROL", 8, MUTED).pack(anchor="w", padx=22, pady=(4, 26))
        self.nav_buttons = {}
        items = [("overview", "Κάμερα"), ("gestures", "Χειρονομίες"),
                 ("response", "Απόκριση"), ("distance", "Απόσταση"), ("system", "Σύστημα")]
        for key, text in items:
            button = tk.Button(nav, text=text, anchor="w", padx=15, pady=13, bd=0,
                               bg=NAV, fg=MUTED, activebackground=SOFT, activeforeground=TEXT,
                               font=("Segoe UI", 10), cursor="hand2", command=lambda name=key: self.show_page(name))
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = button
        self.label(nav, "DeskEye 0.3\nΧωρίς εγγραφή βίντεο", 8, MUTED,
                   justify="left").pack(side="bottom", anchor="w", padx=20, pady=22)
        main = tk.Frame(shell, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        header = tk.Frame(main, bg=BG)
        header.pack(fill="x", pady=(0, 20))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        self.page_title = self.label(titles, "", 22, TEXT, True, anchor="w")
        self.page_title.pack(fill="x")
        self.page_subtitle = self.label(titles, "", 10, MUTED, anchor="w")
        self.page_subtitle.pack(fill="x", pady=(4, 0))
        self.mode = self.label(header, "  ΔΟΚΙΜΗ  ", 9, TEAL, True, padx=8, pady=8)
        self.mode.configure(bg=SOFT)
        self.mode.pack(side="right", padx=(8, 0))
        footer = tk.Frame(main, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(14, 0))
        ttk.Button(footer, text="Αποθήκευση αλλαγών", style="Accent.TButton", command=self.apply_settings).pack(side="right", padx=(10, 0))
        self.status = self.label(footer, "Έτοιμο · εντολές ήχου ανενεργές", 9, MUTED, anchor="w", wraplength=650, justify="left")
        self.status.pack(side="left", fill="x", expand=True)
        self.page_container = tk.Frame(main, bg=BG)
        self.page_container.pack(fill="both", expand=True)
        self.page_container.rowconfigure(0, weight=1)
        self.page_container.columnconfigure(0, weight=1)
        self.pages = {}
        self.scroll_panels = []
        for key, _ in items:
            page = tk.Frame(self.page_container, bg=BG) if key == "overview" else ScrollPanel(self.page_container)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
            if isinstance(page, ScrollPanel):
                self.scroll_panels.append(page)
        self.build_overview(self.pages["overview"])
        self.build_gestures(self.pages["gestures"].inner)
        self.build_response(self.pages["response"].inner)
        self.build_distance(self.pages["distance"].inner)
        self.build_system(self.pages["system"].inner)
        self.bind_all("<MouseWheel>", self.scroll_page, add="+")
        self.show_page("overview")

    def build_overview(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, minsize=252)
        parent.rowconfigure(0, weight=1)
        camera = tk.Frame(parent, bg=PANEL, highlightthickness=0)
        camera.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        top = tk.Frame(camera, bg=PANEL)
        top.pack(fill="x", padx=16, pady=12)
        self.label(top, "Προεπισκόπηση", 10, MUTED).pack(side="left")
        self.check(top, "Mirror", self.mirror, self.change_mirror).pack(side="right")
        self.preview = tk.Label(camera, text="Πάτησε Έναρξη για την κάμερα", bg="#10100f", fg=MUTED,
                                font=("Segoe UI", 13), width=1, height=1)
        self.preview.pack(fill="both", expand=True, padx=12)
        self.tracking = self.label(camera, "Κάμερα εκτός σύνδεσης", 9, MUTED, anchor="w")
        self.tracking.pack(fill="x", padx=16, pady=(10, 4))
        self.pose_label = self.label(camera, "Κεφάλι: —", 9, MUTED, anchor="w")
        self.pose_label.pack(fill="x", padx=16, pady=(0, 12))
        control_scroll = ScrollPanel(parent)
        control_scroll.grid(row=0, column=1, sticky="nsew")
        controls = control_scroll.inner
        card = self.card(controls, "Έλεγχος")
        self.start_button = ttk.Button(card, text="Έναρξη", style="Accent.TButton", command=self.start)
        self.start_button.pack(fill="x", pady=(12, 8))
        self.stop_button = ttk.Button(card, text="Διακοπή", command=self.stop, state="disabled")
        self.stop_button.pack(fill="x")
        self.check(card, "Ενεργές εντολές ήχου", self.live, self.reset_gestures).pack(anchor="w", pady=(16, 0))
        self.check(card, "Παύση χειρονομιών", self.paused, self.reset_gestures).pack(anchor="w", pady=(4, 0))
        self.label(card, "Esc: παύση όταν είσαι εδώ", 8, MUTED).pack(anchor="w", pady=(7, 0))
        card = self.card(controls, "Αναγνώριση")
        self.gesture_label = self.label(card, "Χέρια: —", 10, MUTED, wraplength=206, justify="left", anchor="w")
        self.gesture_label.pack(fill="x", pady=(10, 10))
        self.action_label = self.label(card, "Καμία εντολή ακόμη", 11, TEAL, True, wraplength=206, justify="left", anchor="w")
        self.action_label.pack(fill="x")
        card = self.card(controls, "Απόσταση")
        self.distance_value = self.label(card, "— cm", 28, TEXT, True)
        self.distance_value.pack(anchor="w", pady=(4, 2))
        self.label(card, "εκτίμηση από την κάμερα", 9, MUTED).pack(anchor="w")
        self.calibrate_button = ttk.Button(card, text="Βαθμονόμηση", command=self.calibrate)
        self.calibrate_button.pack(fill="x", pady=(12, 0))
        self.banner = tk.Label(parent, text="Πάτησε Έναρξη και μετά βαθμονόμησε την απόσταση.",
                               bg=SOFT, fg=TEXT, anchor="w", padx=16, pady=12, font=("Segoe UI", 10))
        self.banner.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def build_gestures(self, page):
        for key, (title, hint, _) in GROUPS.items():
            card = self.card(page, title, hint)
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x")
            self.check(row, "Ενεργή", self.gesture_enabled[key]).pack(side="left")
            ttk.Combobox(row, textvariable=self.gesture_hands[key], values=tuple(HAND_LABELS.values()),
                         state="readonly", width=21).pack(side="right")
            if key == "volume":
                method = tk.Frame(card, bg=PANEL)
                method.pack(fill="x", pady=(14, 0))
                self.label(method, "Κίνηση έντασης", 10, MUTED).pack(side="left")
                ttk.Combobox(method, textvariable=self.volume_gesture, values=tuple(VOLUME_LABELS.values()),
                             state="readonly", width=31).pack(side="right")
                self.label(card, "Με γροθιά, το επιλεγμένο χέρι ελέγχει την ένταση χωρίς play / pause.\n"
                           "Χαλάρωσε πρώτα το χέρι πριν κάνεις V για mute.", 9, MUTED,
                           justify="left", wraplength=690).pack(anchor="w", pady=(10, 0))
            if key in ("play_pause", "mute"):
                self.slider(card, "Χρόνος κρατήματος", "hold_fist" if key == "play_pause" else "hold_victory")
        card = self.card(page, "Επιλογή χεριού")
        self.label(card, "Οποιοδήποτε: λειτουργεί το ένα ή το άλλο χέρι, χωρίς διπλή εντολή.\n"
                   "Και τα δύο μαζί: κάνε την ίδια κίνηση με τα δύο χέρια σχεδόν ταυτόχρονα.\n"
                   "Στο pinch ένωσε αντίχειρα–δείκτη και κράτα τα άλλα δάχτυλα ανοιχτά.",
                   10, MUTED, justify="left", wraplength=730).pack(anchor="w", pady=(10, 0))

    def build_response(self, page):
        card = self.card(page, "Προφίλ", "Διάλεξε προφίλ ή άλλαξε τις τιμές και αποθήκευσε.")
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x")
        for name in PRESETS:
            ttk.Button(row, text=name, command=lambda value=name: self.set_preset(value)).pack(side="left", padx=(0, 8))
        card = self.card(page, "Σταθερότητα και ρυθμός")
        self.slider(card, "Εξομάλυνση κίνησης", "smoothing", "Μεγαλύτερη τιμή: πιο ομαλή κίνηση, με λίγη επιπλέον καθυστέρηση.")
        self.slider(card, "Παύση μεταξύ εντολών", "cooldown", "Αποτρέπει επαναλαμβανόμενα mute, play/pause και αλλαγές κομματιών.")
        card = self.card(page, "Ένταση ήχου")
        self.slider(card, "Κράτημα πριν ενεργοποιηθεί η ένταση", "pinch_hold")
        self.slider(card, "Κίνηση ανά βήμα · ποσοστό ύψους εικόνας", "pinch_step", "Μικρότερη τιμή: πιο ευαίσθητος έλεγχος.")
        self.slider(card, "Διάστημα μεταξύ βημάτων έντασης", "volume_interval", "Μικρότερη τιμή: πιο γρήγορες αλλαγές όταν κινείς το χέρι.")
        self.slider(card, "Δύναμη κάθε βήματος", "volume_steps", "×1 για λεπτές αλλαγές · έως ×5 για πιο απότομη αυξομείωση.")
        card = self.card(page, "Swipe παλάμης")
        self.slider(card, "Απαιτούμενη διαδρομή · ποσοστό πλάτους", "swipe_distance")
        self.slider(card, "Μέγιστος χρόνος διαδρομής", "swipe_window", "Μεγαλύτερη τιμή επιτρέπει πιο αργό swipe. Η κατεύθυνση ακολουθεί το preview.")

    def build_distance(self, page):
        card = self.card(page, "Όριο απόστασης", "Τοποθέτησε την κάμερα κοντά στην οθόνη. Οι τιμές είναι εκτιμήσεις, όχι μέτρηση βάθους.")
        self.field(card, "Γνωστή απόσταση από κάμερα · cm", self.reference)
        self.field(card, "Προειδοποίηση κάτω από · cm", self.threshold)
        self.field(card, "Χρόνος κοντά στο όριο · s", self.alert_delay)
        ttk.Button(card, text="Βαθμονόμηση τώρα", command=self.calibrate).pack(anchor="w", pady=(14, 0))
        self.label(card, "Κοίτα ευθεία και μείνε ακίνητος για 30 frames. Η βαθμονόμηση αποθηκεύεται.\n"
                   "Επανάλαβέ την αν αλλάξεις κάμερα, θέση, φακό ή χρήστη.", 10, MUTED,
                   justify="left", wraplength=690).pack(anchor="w", pady=(10, 0))
        card = self.card(page, "Too close", "Κόκκινο διακριτικό μήνυμα, πάνω στο κέντρο της οθόνης του παραθύρου DeskEye.")
        self.check(card, "Μήνυμα πάνω από τις εφαρμογές", self.overlay_enabled).pack(anchor="w")
        self.check(card, "Ήχος ειδοποίησης", self.sound).pack(anchor="w", pady=(5, 10))
        ttk.Button(card, text="Προεπισκόπηση μηνύματος · 3 s", command=lambda: self.overlay.preview()).pack(anchor="w")
        self.label(card, "Δεν παίρνει την εστίαση και δεν εμποδίζει τα κλικ.\n"
                   "Exclusive fullscreen και οθόνες ασφαλείας Windows μπορεί να το καλύπτουν.",
                   9, MUTED, justify="left", wraplength=690).pack(anchor="w", pady=(12, 0))

    def build_system(self, page):
        card = self.card(page, "Κάμερα και εικόνα")
        self.field(card, "Camera ID · απαιτεί Διακοπή για αλλαγή", self.camera)
        self.check(card, "Mirror / κατοπτρισμένη εικόνα", self.mirror, self.change_mirror).pack(anchor="w", pady=10)
        self.label(card, "Το mirror αλλάζει άμεσα. Το δεξί και αριστερό χέρι παραμένουν τα δικά σου.\n"
                   "Οι κατευθύνσεις swipe είναι πάντα όπως τις βλέπεις στην προεπισκόπηση.",
                   10, MUTED, justify="left", wraplength=690).pack(anchor="w")
        card = self.card(page, "Εκκίνηση Windows", "Προαιρετική εκκίνηση όταν συνδέεσαι στον λογαριασμό σου.")
        self.check(card, "Εκκίνηση DeskEye με τα Windows", self.startup_var).pack(anchor="w")
        self.label(card, "Εφαρμόζεται με Αποθήκευση αλλαγών. Ανοίγει ελαχιστοποιημένο και ξεκινά\n"
                   "την κάμερα με την τελευταία βαθμονόμηση. Οι εντολές ήχου μένουν σε δοκιμή.\n"
                   "Ξετσέκαρέ το και αποθήκευσε για πλήρη απενεργοποίηση.",
                   10, MUTED, justify="left", wraplength=690).pack(anchor="w", pady=(10, 0))
        card = self.card(page, "DeskEye 0.3 · Portable")
        self.label(card, "Η έκδοση Windows περιλαμβάνει την εφαρμογή και τα μοντέλα αναγνώρισης.\n"
                   "Κράτησε μαζί όλα τα αρχεία του πακέτου, στον ίδιο φάκελο.\n\n"
                   "Τα frames επεξεργάζονται στη συσκευή και η εφαρμογή δεν καταγράφει βίντεο.\n"
                   "Το MediaPipe ενδέχεται να στέλνει μετρήσεις απόδοσης / χρήσης στην Google.\n"
                   "Περισσότερα για την ιδιωτικότητα στο README.",
                   10, MUTED, justify="left", wraplength=690).pack(anchor="w", pady=(10, 0))

    def show_page(self, name):
        headings = {"overview": ("Κάμερα", "Εικόνα, απόσταση και αναγνώριση."),
                    "gestures": ("Χειρονομίες", "Κίνηση και χέρι για κάθε εντολή."),
                    "response": ("Απόκριση", "Ευαισθησία, ομαλότητα και χρόνοι."),
                    "distance": ("Απόσταση", "Βαθμονόμηση και ειδοποιήσεις."),
                    "system": ("Σύστημα", "Κάμερα και εκκίνηση Windows.")}
        for key, page in self.pages.items():
            if key == name:
                page.grid()
            else:
                page.grid_remove()
            self.nav_buttons[key].configure(bg=SOFT if key == name else NAV, fg=TEAL if key == name else MUTED)
        self.page_title.configure(text=headings[name][0])
        self.page_subtitle.configure(text=headings[name][1])
        self.current_page = name

    def scroll_page(self, event):
        widget = event.widget
        while widget is not None:
            if isinstance(widget, ScrollPanel):
                widget.canvas.yview_scroll(-int(event.delta / 120), "units")
                return "break"
            widget = getattr(widget, "master", None)
