"""Τα μοντέλα είναι επίσημα MediaPipe assets· τα frames δεν ανεβαίνουν πουθενά."""
from pathlib import Path
import hashlib
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
MODELS = {
    "hand_landmarker": "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1",
    "face_landmarker": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
}


def ensure_models(report=print):
    folder = ROOT / "models"
    frozen = getattr(sys, "frozen", False)
    # Το .exe περιέχει τα μοντέλα του: δεν γράφουμε σε Program Files ή στο
    # προσωρινό bundle του PyInstaller και δεν κάνουμε αυτόματη λήψη στο release.
    if not frozen:
        folder.mkdir(exist_ok=True)
    paths = {}
    for name, checksum in MODELS.items():
        path = folder / f"{name}.task"
        try:
            valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        except OSError as error:
            if not frozen:
                raise
            raise RuntimeError(
                f"Δεν διαβάζεται το μοντέλο {name}. Κατέβασε ξανά και αποσυμπίεσε ολόκληρο το πακέτο DeskEye."
            ) from error
        if not valid:
            if frozen:
                raise RuntimeError(
                    f"Το μοντέλο {name} λείπει ή έχει αλλοιωθεί. "
                    "Κατέβασε ξανά και αποσυμπίεσε ολόκληρο το πακέτο DeskEye."
                )
            report(f"Λήψη μοντέλου: {name}…")
            url = f"https://storage.googleapis.com/mediapipe-models/{name}/{name}/float16/1/{name}.task"
            with urlopen(url, timeout=45) as response:
                data = response.read(30_000_000)
            if hashlib.sha256(data).hexdigest() != checksum:
                raise RuntimeError(f"Απέτυχε ο έλεγχος SHA-256: {name}")
            # Γράφουμε atomically: μια διακοπή δεν αφήνει μισό μοντέλο.
            partial = path.with_suffix(".part")
            partial.write_bytes(data)
            partial.replace(path)
        paths[name] = str(path)
    return paths


def load_model_buffers(report=print):
    """Η Python διαβάζει Unicode paths σωστά, ενώ το native fopen του MediaPipe όχι.

    Δίνουμε bytes αντί για filename στο C API, για φακέλους όπως «Λήψεις».
    Ελέγχουμε το ακριβές buffer που θα φορτωθεί, ακόμη αν άλλαξε στο μεταξύ το αρχείο.
    """
    buffers = {}
    for name, path in ensure_models(report).items():
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != MODELS[name]:
            raise RuntimeError(f"Το μοντέλο {name} άλλαξε κατά τη φόρτωση. Εξάγαγε ξανά το πακέτο.")
        buffers[name] = data
    return buffers
