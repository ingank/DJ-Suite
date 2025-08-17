import time
import datetime
from pathlib import Path
from lib.utils import find_audio_files

THRESHOLD = 0.3  # Sekunden
BLOCKSIZE = 1024 * 1024  # 1 MB

# Logdatei benennen mit Datum/Zeit
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
logfile = Path(f"measure-{stamp}.log")

# Alle FLAC-Dateien rekursiv suchen (relativ zur cwd)
files = find_audio_files(".", absolute=False, filter_ext=[".flac"])

with logfile.open("w", encoding="utf-8") as log:
    log.write(f"# Messung gestartet: {stamp}\n")
    log.write(f"# Gefundene Dateien: {len(files)}\n\n")

    for relpath in files:
        file = Path(".") / relpath
        t0 = time.perf_counter()
        with open(file, "rb") as f:
            while f.read(BLOCKSIZE):
                pass
        dt = time.perf_counter() - t0

        # Immer auf den Bildschirm
        print(f"[measure] {dt:.4f}s {relpath}")

        # Nur langsame ins Log
        if dt > THRESHOLD:
            log.write(f"[slow] {dt:.4f}s {relpath}\n")

print(f"\n[INFO] Ausreißer > {THRESHOLD:.1f}s in {logfile} gespeichert.")
