"""
loudness.py

Misst die Lautheit (LUFS) aller Audio-Dateien rekursiv im aktuellen Verzeichnis und allen Unterordnern.
Für FLAC-Dateien wird ein LUFS-Tag automatisch ergänzt, falls noch nicht vorhanden (auf 1 Nachkommastelle).
Gibt die Ergebnisse tabellarisch mit Status (R/W) aus.

Nutzt lib.soundfile für die Analyse und lib.tagging für Tagging-Operationen.
"""

from pathlib import Path
from lib.utils import find_audio_files
from lib.soundfile import loudness
from lib.tagging import get_tag, set_tags


def main():
    root = Path('.').resolve()
    print(f"{'R/W':>3}  {'LUFS':>8}  Pfad")
    print("-" * 50)

    count = 0
    errors = 0

    for rel_path in find_audio_files(root):
        file = root / rel_path
        try:
            mode = "R"
            lufs = None
            lufs_tag = None
            if file.suffix.lower() == ".flac":
                lufs_tag = get_tag(file, "LUFS")
            if lufs_tag is not None:
                try:
                    lufs = float(lufs_tag)
                except Exception:
                    lufs = None
            if lufs is None:
                lufs, _ = loudness(file)
                if file.suffix.lower() == ".flac" and lufs is not None:
                    set_tags(file, LUFS=f"{lufs:.1f}")
                    mode = "W"
            lufs_str = f"{lufs:8.2f}" if lufs is not None else "   n/a  "
            print(f"{mode:>3}  {lufs_str}  {rel_path}")
            count += 1
        except Exception as e:
            print(f"[FEHLER] {rel_path}: {e}")
            errors += 1
    print("-" * 50)
    print(f"{count} Dateien verarbeitet, {errors} Fehler.")


if __name__ == "__main__":
    main()
