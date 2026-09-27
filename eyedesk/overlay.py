"""Διακριτικό, ανεξάρτητο Too close overlay χωρίς focus ή δέσμευση του ποντικιού.

Το TOPMOST λειτουργεί πάνω από κανονικά / borderless παράθυρα. Τα Windows δεν
εγγυώνται overlay πάνω από exclusive fullscreen, secure desktop ή οθόνη κλειδώματος.
"""
import ctypes
from ctypes import wintypes
import os
import time
import tkinter as tk

COLOR_KEY = "#010203"


def centered_bounds(left, top, right, width=250):
    return left + max(0, (right - left - width) // 2), top + 24


class Overlay:
    def __init__(self, root):
        self.root = root
        self.alert = False
        self.preview_until = 0.0
        self.visible = False
        self.closed = False
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("DeskEye · Too close")
        self.window.overrideredirect(True)
        self.window.configure(bg=COLOR_KEY)
        self.window.attributes("-topmost", True)
        self.window.geometry("250x52+0+24")
        canvas = tk.Canvas(self.window, width=250, height=52, bg=COLOR_KEY,
                           highlightthickness=0, takefocus=False)
        canvas.pack(fill="both", expand=True)
        # Μικρή σκιά για αντίθεση και σε λευκό παράθυρο, χωρίς μεγάλο κόκκινο πλαίσιο.
        canvas.create_text(126, 27, text="Too close", fill="#22171b", font=("Segoe UI", 21, "bold"))
        canvas.create_text(125, 26, text="Too close", fill="#ff505b", font=("Segoe UI", 21, "bold"))
        self.hwnd = None
        self.api = None
        self.window.update_idletasks()
        if os.name == "nt":
            self.window.attributes("-transparentcolor", COLOR_KEY)
            self.window.attributes("-toolwindow", True)
            self.api = ctypes.WinDLL("user32", use_last_error=True)
            self.api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            self.api.GetAncestor.restype = wintypes.HWND
            self.api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            self.api.GetWindowLongW.restype = wintypes.LONG
            self.api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
            self.api.SetWindowLongW.restype = wintypes.LONG
            self.api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                              ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            self.api.SetWindowPos.restype = wintypes.BOOL
            self.api.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            self.api.ShowWindow.restype = wintypes.BOOL
            self.api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            self.api.MonitorFromWindow.restype = wintypes.HANDLE
            self.hwnd = self.api.GetAncestor(self.window.winfo_id(), 2)
            style = self.api.GetWindowLongW(self.hwnd, -20)
            # LAYERED + TRANSPARENT = click-through, NOACTIVATE = δεν κλέβει πληκτρολόγηση.
            self.api.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x20 | 0x08000000 | 0x80)
        self.timer = root.after(300, self.tick)

    def set_alert(self, enabled):
        self.alert = bool(enabled)
        self.refresh()

    def preview(self):
        self.preview_until = time.monotonic() + 3
        self.refresh()

    def bounds(self):
        left, top, right = 0, 0, self.root.winfo_screenwidth()
        if self.api is not None:
            class MonitorInfo(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            self.api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
            self.api.GetMonitorInfoW.restype = wintypes.BOOL
            monitor = self.api.MonitorFromWindow(self.root.winfo_id(), 2)
            if self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
                left, top, right = info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right
        return centered_bounds(left, top, right)

    def refresh(self):
        if self.closed:
            return
        show = self.alert or time.monotonic() < self.preview_until
        if show:
            x, y = self.bounds()
            if not self.visible:
                # SW_SHOWNOACTIVATE προτιμάται από deiconify που μπορεί να αλλάξει focus.
                if self.api is not None:
                    self.api.ShowWindow(self.hwnd, 4)
                else:
                    self.window.deiconify()
                self.visible = True
            if self.api is not None:
                self.api.SetWindowPos(self.hwnd, -1, x, y, 250, 52, 0x0010 | 0x0040)
            else:
                self.window.geometry(f"250x52+{x}+{y}")
        elif self.visible:
            if self.api is not None:
                self.api.ShowWindow(self.hwnd, 0)
            else:
                self.window.withdraw()
            self.visible = False

    def tick(self):
        self.refresh()
        if not self.closed:
            self.timer = self.root.after(700, self.tick)

    def hide(self):
        self.alert = False
        self.preview_until = 0
        self.refresh()

    def close(self):
        self.closed = True
        self.root.after_cancel(self.timer)
        self.window.destroy()
