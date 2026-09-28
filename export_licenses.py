"""Αντιγράφει τα αυθεντικά notices του build environment, χωρίς αλλαγή κειμένου."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent
destination = root / "licenses"
destination.mkdir(exist_ok=True)
inventory = []
for distribution in metadata.distributions():
    name = distribution.metadata["Name"]
    inventory.append(f"{name}=={distribution.version}")
    for entry in distribution.files or []:
        # Περιλαμβάνουμε bundled τρίτες βιβλιοθήκες (OpenBLAS, codecs, fonts κ.λπ.).
        if not any(token in entry.name.lower() for token in ("license", "licence", "copying", "notice", "copyright")):
            continue
        source = Path(distribution.locate_file(entry))
        if not source.is_file():
            continue
        safe_parts = [part for part in entry.parts if part not in ("..", ".")]
        target = destination / name / Path(*safe_parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
base = Path(sys.base_prefix)
shutil.copyfile(base / "LICENSE.txt", destination / "Python-LICENSE.txt")
for component in ("tcl8.6", "tk8.6"):
    source = base / "tcl" / component / "license.terms"
    if source.exists():
        shutil.copyfile(source, destination / f"{component}-license.terms")
(destination / "BUILD-INVENTORY.txt").write_text("\n".join(sorted(inventory)) + "\n", encoding="utf-8")
print(f"Preserved notices for {len(inventory)} build dependencies in {destination}")
