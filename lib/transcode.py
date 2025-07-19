# lib/transcode.py

import subprocess
import shutil
import os
from mutagen.flac import FLAC
# <-- zentrale Kontrolle der erlaubten Endungen
from lib.config import AUDIO_EXTENSIONS


def to_flac(src, dst_flac, flac_copy=True):
    """
    Transcodiert eine Audio-Datei zu FLAC.
    Nur Formate, die in config.py erlaubt sind (AUDIO_EXTENSIONS).
    FLAC: kopiert, wenn flac_copy=True, sonst neu encodiert.
    MP3: immer 16 Bit + Dither, andere Formate: Original-Bittiefe.
    """
    ext = os.path.splitext(src)[1].lower()
    if ext not in AUDIO_EXTENSIONS:
        raise ValueError(f"Nicht unterstütztes Format: {src} (Endung: {ext})")

    if ext == ".flac":
        if flac_copy:
            shutil.copy2(src, dst_flac)
            print(f"[OK] FLAC kopiert: {src} → {dst_flac}")
            return
        else:
            print(f"[INFO] FLAC wird neu codiert: {src} → {dst_flac}")
            mp3_mode = False
    elif ext == ".mp3":
        mp3_mode = True
    else:
        mp3_mode = False

    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(src), '-c:a', 'flac'
    ]
    if mp3_mode:
        ffmpeg_cmd.extend([
            '-sample_fmt', 's16',
            '-af', 'aresample=resampler=soxr:dither_method=shibata'
        ])
    else:
        ffmpeg_cmd.extend([
            '-af', 'aresample=resampler=soxr'
        ])
    ffmpeg_cmd.append(str(dst_flac))

    try:
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[OK] Konvertiert: {src} → {dst_flac}")
    except subprocess.CalledProcessError as e:
        print(f"[FEHLER] Fehler bei der Konvertierung: {src} → {dst_flac}")
        raise e


def to_bag(src_flac, dst_dir, overwrite=False):
    """
    Transkodiert eine FLAC-Datei in 24/44.1 FLAC und speichert sie mit dem Dateinamen,
    der aus dem Tag 'GEN0-SHA256' der Eingangsdatei erzeugt wird.
    """
    # 1. Tag auslesen
    audio = FLAC(src_flac)
    sha256 = audio.get('GEN0-SHA256', [None])[0]
    if not sha256:
        raise ValueError(f"GEN0-SHA256 Tag nicht gefunden in {src_flac}")

    out_name = f"{sha256}.flac"
    dst_path = os.path.join(dst_dir, out_name)

    # 2. Existenz prüfen
    if os.path.exists(dst_path) and not overwrite:
        print(f"[SKIP] Ziel existiert bereits: {dst_path}")
        return dst_path

    # 3. Transkodierung
    ffmpeg_cmd = [
        'ffmpeg', '-y' if overwrite else '-n', '-i', str(src_flac),
        '-c:a', 'flac',
        '-sample_fmt', 's32',
        '-ar', '44100',
        '-af', 'aresample=resampler=soxr'
    ]
    ffmpeg_cmd.append(str(dst_path))

    try:
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        print(f"[OK] {src_flac} → {dst_path}")
    except subprocess.CalledProcessError as e:
        print(f"[FEHLER] Fehler bei Transcodierung: {src_flac} → {dst_path}")
        raise e

    return dst_path
