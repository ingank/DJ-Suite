r"""
push.py

Kopiert und normalisiert alle FLAC-Dateien aus dem Ordner STAGE/ in den zentralen Zielordner "Engine Base" 
(im Benutzer-Musikverzeichnis, z. B. C:\Users\<Benutzer>\Music\Engine Base).
Jede Zieldatei wird auf ein Ziel-Lautheitslevel (z. B. -21 LUFS) normalisiert und als {GEN0-ID}.flac abgelegt.
Der COMMENT-Tag wird nach dem Kopieren korrigiert (description → COMMENT).
Bestehende Dateien werden überschrieben.

Autor: [Ingolf Ankert]
Version: 1.1
"""

import os
from pathlib import Path
from mutagen.flac import FLAC
import subprocess

TARGET_LUFS = -21.0  # Ziel-Lautheit für die Normalisierung

def get_engine_base_dir():
    home = Path.home()
    music = home / "Music"
    engine_base = music / "Engine Base"
    engine_base.mkdir(parents=True, exist_ok=True)
    return engine_base

def ensure_flac_comment_tag(output_file):
    """Korrigiert Kommentar-Tag: description → COMMENT"""
    flac_file = FLAC(output_file)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()

def normalize_file(file, lufs_diff, output_file):
    """
    Normalisiert die Lautheit einer Datei per ffmpeg ('volume'-Filter).
    Speichert als FLAC.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        'ffmpeg', '-y', '-i', str(file),
        '-af', f'volume={lufs_diff}dB',
        '-c:a', 'flac',
        str(output_file)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

STAGE_DIR = Path(".")
OUT_DIR = get_engine_base_dir()

for flac_file in STAGE_DIR.glob("*.flac"):
    try:
        audio = FLAC(flac_file)
        gen0_id = audio.get("GEN0-ID", [None])[0]
        gen0_lufs = audio.get("GEN0-LUFS", [None])[0]
        if not gen0_id or gen0_lufs is None:
            print(f"Kein GEN0-ID oder GEN0-LUFS Tag in {flac_file} – übersprungen.")
            continue

        dest_file = OUT_DIR / f"{gen0_id}.flac"
        lufs_diff = TARGET_LUFS - float(gen0_lufs)
        normalize_file(flac_file, lufs_diff, dest_file)
        ensure_flac_comment_tag(dest_file)
        print(f"Normalisiert & kopiert: {flac_file.name} → {dest_file.name} (Delta: {lufs_diff:+.1f} dB)")
    except Exception as e:
        print(f"Fehler bei {flac_file}: {e}")

print("Rollout abgeschlossen.")
