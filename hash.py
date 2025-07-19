"""
hash.py

Erzeugt für alle Audiodateien im aktuellen Verzeichnis (rekursiv) eine
SHA256-Hashliste. Das Skript bricht beim ersten Fehler sofort ab und meldet,
wie viele Dateien bis dahin erfolgreich verarbeitet wurden. Bei fehlerfreiem
Durchlauf wird die Gesamtanzahl bestätigt.

Audio-Formate und Pipeline sind über lib.config/lib.sha256 zentral definiert.

Ergebnis: sha256-hashes-YYYY-mm-dd_HH-MM-SS.txt im aktuellen Verzeichnis.

Sicherer Workflow für sensible oder wertvolle Audiodaten.
"""

from pathlib import Path
from lib.soundfile import sha256
from lib.utils import find_audio_files, get_timestamp


def main():
    timestamp = get_timestamp()
    outfilename = f"sha256-hashes-{timestamp}.txt"
    root = Path('.').resolve()

    processed = 0

    try:
        with open(outfilename, 'w', encoding='utf-8') as out:
            for relpath in find_audio_files(root):
                hashval = sha256(root / relpath)
                print(hashval)
                print(relpath.parent.as_posix())
                print(relpath.name)
                print()
                out.write(f"{hashval} {relpath.as_posix()}\n")
                processed += 1
    except Exception as e:
        print(f"\n[ABBRUCH] Fehler bei {relpath}: {e}")
        print(f"Bis zum Fehler wurden {processed} Dateien verarbeitet.")
        raise  # Optional: für Stacktrace

    print(
        f"\nAlle {processed} Dateien wurden erfolgreich verarbeitet – KEIN Fehler aufgetreten!")


if __name__ == "__main__":
    main()
