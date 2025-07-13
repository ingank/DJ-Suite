"""
stage.py

Konvertiert alle Audiodateien im aktuellen Verzeichnis in hochwertige FLACs (24bit/44.1kHz, soxr-Resampler)
und speichert sie im Unterordner STAGE/.
Die eindeutige GEN0-ID (SHA256 des 16bit PCM-RAW-Streams, CD-Format),
sowie der Originaldateiname, LUFS und LRA werden als Tags geschrieben.
Außerdem wird (soweit vorhanden) der FLAC-Tag 'description' in das Standardfeld 'COMMENT' übertragen.

Autor: [Ingolf Ankert]
Version: 1.4
"""

import os
import re
import hashlib
import subprocess
import tempfile
from pathlib import Path
from mutagen.flac import FLAC

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.mp3', '.flac']
IN_DIR = Path('.')
OUT_DIR = IN_DIR / "STAGE"
OUT_DIR.mkdir(exist_ok=True)


def ensure_flac_comment_tag(file):
    """
    Korrigiert Kommentar-Tag für FLAC-Kompatibilität:
    Falls das Feld 'description' existiert,
    wird dessen Inhalt ins Standardfeld 'COMMENT' übertragen.
    Dadurch ist der Kommentar in allen Playern und Tag-Editoren sichtbar.
    """
    flac_file = FLAC(file)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        flac_file.save()


def sound_params(file):
    """
    Extrahiert aus einer Audiodatei (nur erster Audiostream):
      - SHA256-Hash des 16bit PCM RAW-Streams (Stereo, 44.1kHz, CD-Format)
      - Integrated Loudness (LUFS)
      - Loudness Range (LRA)
    Gibt (sha256_hex, lufs, lra) zurück.
    """
    with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as tmpfile:
        tmp_raw = tmpfile.name
    try:
        # 1. PCM-RAW aus Datei extrahieren (CD-Format, 16bit)
        subprocess.run([
            'ffmpeg', '-y', '-i', str(file),
            '-map', '0:a:0',
            '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
            '-f', 's16le', tmp_raw
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        # 2. SHA256 berechnen
        with open(tmp_raw, 'rb') as f:
            sha256_hex = hashlib.sha256(f.read()).hexdigest()

        # 3. Loudness-Analyse mit ffmpeg (auf dem 16bit-PCM-Stream)
        result = subprocess.run([
            'ffmpeg', '-f', 's16le', '-ar', '44100', '-ac', '2', '-i', tmp_raw,
            '-filter_complex', 'ebur128=framelog=quiet',
            '-f', 'null', '-'
        ], stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        lufs = lra = None
        in_summary = False
        for line in result.stderr.splitlines():
            if 'Summary:' in line:
                in_summary = True
            elif in_summary and 'I:' in line and 'LUFS' in line:
                m = re.search(r'I:\s*(-?\d+\.\d+)\s*LUFS', line)
                if m:
                    lufs = float(m.group(1))
            elif in_summary and 'LRA:' in line and 'LU' in line:
                m = re.search(r'LRA:\s*(-?\d+\.\d+)\s*LU', line)
                if m:
                    lra = float(m.group(1))
            if in_summary and (lufs is not None) and (lra is not None):
                break
        return sha256_hex, lufs, lra
    finally:
        if os.path.exists(tmp_raw):
            os.remove(tmp_raw)


for file in IN_DIR.iterdir():
    if file.is_file() and file.suffix.lower() in AUDIO_EXTENSIONS:
        outname = f"{file.stem}{file.suffix}.flac"
        outpath = OUT_DIR / outname

        print(f"Konvertiere {file} → {outname}")

        # 1. Transkodieren in hochwertige FLAC-Datei (24bit!)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(file),
            "-ar", "44100", "-ac", "2",
            "-sample_fmt", "s32",  # 24bit FLAC (ffmpeg verwendet s32)
            "-af", "aresample=resampler=soxr",
            str(outpath)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. Kommentar-Tag ggf. korrigieren
        ensure_flac_comment_tag(outpath)

        # 3. Analyse: SHA256, Loudness, Loudness Range aus 16bit PCM-Stream
        gen0_id, lufs, lra = sound_params(file)

        # 4. Tags schreiben
        audio = FLAC(outpath)
        audio["GEN0-ID"] = gen0_id
        audio["GEN0-FILENAME"] = file.name
        if lufs is not None:
            audio["GEN0-LUFS"] = str(lufs)
        if lra is not None:
            audio["GEN0-LRA"] = str(lra)
        audio.save()

        print(f"→ Tags: ID={gen0_id[:12]}..., LUFS={lufs}, LRA={lra}")

print("Alle Dateien verarbeitet.")
