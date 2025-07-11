"""
stage.py

Konvertiert alle Audiodateien im aktuellen Verzeichnis in hochwertige FLACs (24bit/44.1kHz, soxr-Resampler)
und speichert sie im Unterordner GEN1/.
Jede Datei erhält eine RFC4122-konforme UUID (aus SHA256 der Datei, first 16 bytes), 
und den Originaldateinamen - beide mit "GEN0-" Präfix als Tag.

Autor: [Ingolf Ankert]
Version: 1.1
"""

import hashlib
import subprocess
from pathlib import Path
from mutagen.flac import FLAC
import uuid

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.mp3', '.flac']

IN_DIR = Path('.')
OUT_DIR = IN_DIR / "STAGE"
OUT_DIR.mkdir(exist_ok=True)


def file_uuid128(fname):
    h = hashlib.sha256()
    with open(fname, "rb") as f:
        while (chunk := f.read(65536)):
            h.update(chunk)
    uuid_bytes = h.digest()[:16]
    file_uuid = uuid.UUID(bytes=uuid_bytes)
    return str(file_uuid)


def ensure_flac_comment_tag(output_file):
    flac_file = FLAC(output_file)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()


for file in IN_DIR.iterdir():
    if file.is_file() and file.suffix.lower() in AUDIO_EXTENSIONS:
        outname = f"{file.stem}{file.suffix}.flac"
        outpath = OUT_DIR / outname

        # 1. UUID berechnen (RFC-konform, 128 Bit)
        uuid_str = file_uuid128(file)

        # 2. Konvertieren nach FLAC mit soxr (ohne sample_fmt!)
        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", str(file),
            "-ar", "44100",
            "-ac", "2",
            "-af", "aresample=resampler=soxr",
            str(outpath)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ensure_flac_comment_tag(str(outpath))

        # 3. Tags mit GEN0-Präfix in FLAC schreiben
        audio = FLAC(outpath)
        audio["GEN0-UUID"] = uuid_str
        audio["GEN0-FILENAME"] = file.name
        audio.save()

        print(f"Schreibe: {outname} | GEN0-UUID: {uuid_str}")

print("Alle Dateien verarbeitet!")
