"""Σημείο εισόδου. Τρέξε python main.py ή διπλό κλικ στο START.cmd."""
import multiprocessing
import os
import argparse
import sys
from eyedesk.runtime import DATA, InstanceLock

# Η cache μένει δίπλα στο project και δεν μπλέκει με την προσωπική Python cache.
os.environ.setdefault("MPLCONFIGDIR", str(DATA / "matplotlib"))


if __name__ == "__main__":
    # Στο windowed .exe δεν υπάρχει κονσόλα. Ορισμένες βιβλιοθήκες γράφουν
    # στο stderr ακόμη κι έτσι, επομένως δίνουμε ένα έγκυρο stream.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # Απαραίτητο στα Windows: δεν ανοίγουμε δεύτερη GUI μέσα στον camera worker.
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="DeskEye desktop companion")
    parser.add_argument("--startup", action="store_true", help="Start camera and minimize after Windows logon")
    parser.add_argument("--self-test", metavar="REPORT", help="Check bundled models and GUI without opening a camera")
    args = parser.parse_args()
    if args.self_test:
        from eyedesk.diagnostics import self_test
        raise SystemExit(self_test(args.self_test))
    import logging
    from logging.handlers import RotatingFileHandler
    DATA.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.WARNING, handlers=[RotatingFileHandler(
        DATA / "deskeye.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")])
    from eyedesk.app import App
    lock = InstanceLock()
    if lock.acquire():
        try:
            app = App(auto_start=args.startup)
            def report_error(kind, value, traceback):
                logging.error("GUI callback failed", exc_info=(kind, value, traceback))
                app.status.configure(text="Παρουσιάστηκε σφάλμα. Οι λεπτομέρειες γράφτηκαν στο deskeye.log.")
                app.live.set(False)
                app.reset_gestures()
            app.report_callback_exception = report_error
            app.mainloop()
        except Exception:
            logging.exception("Application startup failed")
            from tkinter import messagebox
            messagebox.showerror("DeskEye", f"Δεν ξεκίνησε η εφαρμογή.\nΛεπτομέρειες: {DATA / 'deskeye.log'}")
        finally:
            lock.release()
    elif not args.startup:
        from tkinter import Tk, messagebox
        window = Tk()
        window.withdraw()
        messagebox.showinfo("DeskEye", "Το DeskEye εκτελείται ήδη. Άνοιξέ το από τη γραμμή εργασιών.", parent=window)
        window.destroy()
