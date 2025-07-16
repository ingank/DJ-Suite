"""
filecopy.py

Kopiert alle in einer Hashdatei aufgeführten Dateien
in einen Unterordner "DIFF" (im aktuellen Verzeichnis).

Die Hashdatei muss folgendes Format haben:
    <sha256> <relativer/pfad/zur/datei>

Jede Datei wird aus dem angegebenen Pfad gesucht und
mit ihrem Dateinamen in "DIFF" gespeichert.

Benutzung:
    python filecopy.py hashdatei.txt
"""

import sys
from pathlib import Path
import shutil

# --- Argumentprüfung ---
if len(sys.argv) != 2:
    print("Aufruf: python filecopy.py hashdatei.txt")
    sys.exit(1)

hashfile = sys.argv[1]
DIFF_DIR = Path('.') / 'DIFF'
DIFF_DIR.mkdir(exist_ok=True)  # Ordner anlegen, falls nicht vorhanden

# --- Hashdatei verarbeiten ---
with open(hashfile, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            print(f"WARNUNG: Ungültige Zeile übersprungen: {line}")
            continue
        _, relpath = parts
        src = Path(relpath)
        dst = DIFF_DIR / src.name
        if not src.exists():
            print(f"WARNUNG: Datei nicht gefunden: {src}")
            continue
        try:
            shutil.copy2(src, dst)
            print(f"Kopiert: {src} -> {dst}")
        except Exception as e:
            print(f"FEHLER beim Kopieren von {src}: {e}")

print(f"\nAlle vorhandenen Dateien wurden in den Ordner {DIFF_DIR} kopiert.")
