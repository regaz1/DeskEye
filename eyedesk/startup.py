"""Προαιρετικό autostart μόνο για τον τρέχοντα χρήστη, χωρίς administrator.

Η εφαρμογή γράφει ΜΟΝΟ τη δική της τιμή DeskEye στο HKCU Run και μόνο όταν
ο χρήστης εφαρμόσει αλλαγή της αντίστοιχης επιλογής. Δεν το ενεργοποιούμε με tests.
"""
from pathlib import Path
import subprocess
import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "DeskEye"
LEGACY_VALUE = "EyeDesk"


def command(executable=None, root=None, frozen=None):
    executable = Path(executable or sys.executable).resolve()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        args = [str(executable), "--startup"]
    else:
        # pythonw αποφεύγει ένα επιπλέον παράθυρο κονσόλας κατά το logon.
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
        root = Path(root or Path(__file__).resolve().parent.parent)
        args = [str(executable), str((root / "main.py").resolve()), "--startup"]
    result = subprocess.list2cmdline(args)
    if len(result) > 260:
        raise ValueError("Η διαδρομή είναι πολύ μεγάλη για εκκίνηση με Windows. Μετέφερε το DeskEye σε μικρότερη διαδρομή.")
    return result


def read_command(value):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, value)[0]
    except FileNotFoundError:
        return None


def current_command():
    return read_command(VALUE) or read_command(LEGACY_VALUE)


def set_enabled(enabled):
    import winreg
    desired = command() if enabled else None
    legacy = read_command(LEGACY_VALUE)
    if desired == current_command() and legacy is None:
        return  # Δεν ξαναγράφουμε το Run key σε κάθε εκκίνηση της εφαρμογής.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, desired)
        else:
            try:
                winreg.DeleteValue(key, VALUE)
            except FileNotFoundError:
                pass
        # Μεταφέρουμε μόνο το δικό μας παλιό autostart, όταν εφαρμόζεται ρύθμιση.
        # Έτσι η μετονομασία δεν αφήνει δύο εφαρμογές να ανοίγουν την ίδια κάμερα.
        if legacy is not None:
            try:
                winreg.DeleteValue(key, LEGACY_VALUE)
            except FileNotFoundError:
                pass
