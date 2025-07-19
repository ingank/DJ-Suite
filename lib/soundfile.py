# lib/soundfile.py

import subprocess
import hashlib
import subprocess
import shutil
import os
import re
from mutagen.flac import FLAC
from lib.config import AUDIO_EXTENSIONS


def sha256(file):
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(file),
        '-map', '0:a:0',
        '-vn', '-acodec', 'pcm_s24le', '-ar', '96000', '-ac', '2',
        '-f', 's24le', '-'
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    hasher = hashlib.sha256()
    while True:
        chunk = proc.stdout.read(1024 * 1024)
        if not chunk:
            break
        hasher.update(chunk)
    proc.wait()
    return hasher.hexdigest()


def loudness(file):
    ffmpeg_cmd = [
        'ffmpeg', '-hide_banner', '-nostats',
        '-i', str(file),
        '-map', '0:a:0',
        '-af', 'ebur128',
        '-f', 'null', '-'
    ]

    # Wichtig: encoding="utf-8", errors="replace"
    result = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace"
    )

    stderr = result.stderr
    lufs = lra = None
    in_summary = False

    for line in stderr.splitlines():
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

    return lufs, lra


def to_stage(src, dst_flac, flac_copy=True):
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
            # print(f"[OK] FLAC kopiert: {src} → {dst_flac}")
            return
        else:
            # print(f"[INFO] FLAC wird neu codiert: {src} → {dst_flac}")
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
        # print(f"[OK] Konvertiert: {src} → {dst_flac}")
    except subprocess.CalledProcessError as e:
        # print(f"[FEHLER] Fehler bei der Konvertierung: {src} → {dst_flac}")
        raise e


def to_bag(src_flac, dst_flac, src_lufs, target_lufs):
    """
    Transkodiert src_flac nach dst_flac, normalisiert auf target_lufs (in dB LUFS).
    Annahme: Input ist FLAC, Output immer FLAC, 24bit, 44.1kHz.
    """
    lufs_diff = target_lufs - src_lufs  # z.B. -21.0 - (-13.2) = -7.8dB Gain
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(src_flac),
        '-af', f'volume={lufs_diff:.1f}dB,aresample=resampler=soxr',
        '-c:a', 'flac',
        '-sample_fmt', 's32',   # 24bit in FLAC
        '-ar', '44100',
        str(dst_flac)
    ]
    result = subprocess.run(
        ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
