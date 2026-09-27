"""Διαδρομές δεδομένων και μία συνεδρία εφαρμογής ανά εγκατάσταση."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DATA = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "EyeDesk"
        if getattr(sys, "frozen", False) else ROOT / ".local")


class InstanceLock:
    def __init__(self, directory=DATA):
        self.path = Path(directory) / "instance.lock"
        self.file = None

    def acquire(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            self.file.close()
            self.file = None
            return False

    def release(self):
        if self.file is not None:
            # Το κλείσιμο αποδεσμεύει το file lock ακόμη και μετά από crash.
            self.file.close()
            self.file = None
