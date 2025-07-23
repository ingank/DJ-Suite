"""
stage.py

Batch-Konvertierung aller Audiodateien im aktuellen Verzeichnis (rekursiv) ins STAGE-Format (FLAC),
inkl. SHA256-Tagging. Zielordner ist ein Zeitstempel-Ordner unterhalb von STAGE_ROOT.
Abhängigkeiten: lib.transcode, lib.sha256, lib.tagging, lib.config, lib.utils
"""

import os
from pathlib import Path
from lib.soundfile import sha256, to_stage
from lib.tagging import set_tags, touch_comment
from lib.config import STAGE_ROOT, AUDIO_EXTENSIONS
from lib.utils import find_audio_files, get_timestamp


def shortpath(p, width=100):
    s = str(p)
    if len(s) <= width:
        return s
    return "…" + s[-(width-1):]  # Erstes Zeichen Ellipse, dann der letzte Teil


def main():
    timestamp = get_timestamp()
    stage_dir = Path(STAGE_ROOT) / timestamp

    os.makedirs(stage_dir, exist_ok=True)

    print(f"[INFO] Starte Stage-Transkodierung in: {stage_dir}")
    print(f"[INFO] Unterstützte Endungen: {AUDIO_EXTENSIONS}\n")

    files = list(find_audio_files(Path('.').resolve()))
    if not files:
        print("[INFO] Keine Audiodateien gefunden. Nichts zu tun.")
        return

    ok, err = 0, 0
    error_files = []  # Liste für Fehlerdateien

    for relpath in files:
        file = Path('.') / relpath
        dst_flac = stage_dir / relpath.with_suffix(".flac")
        os.makedirs(dst_flac.parent, exist_ok=True)
        try:
            # Transkodierung ins Stage-Format (FLAC)
            to_stage(file, dst_flac)
            # SHA256 berechnen
            sha = sha256(file)
            # FLAC-Kommentar ggf. anpassen
            touch_comment(dst_flac)
            # GEN0-SHA256-Tag setzen
            set_tags(dst_flac, {"GEN0-SHA256": sha})

            print(f"[ORIGINAL] {shortpath(relpath)}")
            print(
                f"[OUTPUT]   STAGE_ROOT\\{timestamp}\\{shortpath(dst_flac.name)}")
            print(f"[GETAGGT]  {sha}")
            ok += 1
        except Exception as e:
            print(f"\n\n\n")
            print(f"[FEHLER] bei {file}: {e}")
            print(f"\n\n\n")
            err += 1
            error_files.append(str(file))  # Fehlerdatei merken
        print()

    print(f"\n[INFO] {ok} Dateien verarbeitet, {err} Fehler.")
    if error_files:
        print("[FEHLERLISTE]")
        for f in error_files:
            print(f"- {f}")
    print("[ENDE] Stage-Prozess abgeschlossen.")


if __name__ == "__main__":
    main()
