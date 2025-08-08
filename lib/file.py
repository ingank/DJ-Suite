"""
lib/file.py

Zentrale Library für Audio-Hashing, Loudness-Messung, FLAC-Konvertierung und FLAC-Tagging.
Wird verwendet zur Vorbereitung, Analyse und Verwaltung von Audio-Tracks im Produktionsworkflow.
"""

import subprocess
import hashlib
import shutil
import re
import os
from mutagen.flac import FLAC
from lib.config import AUDIO_EXTENSIONS


# === Audioanalyse & Konvertierung ===

def sha256(file):
    """
    Berechnet den SHA-256-Hash des Audiostreams einer Datei.
    Verwendet PCM 24bit/96kHz Stereo als normiertes Zwischenformat.
    Dient zur eindeutigen Wiedererkennung (MX-ID).
    Eingabeformat ist flexibel (z. B. MP3, FLAC, WAV).
    Gibt hexadezimale Hash-Zeichenkette zurück.
    """
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
    """
    Misst LUFS und Loudness Range (LRA) mit ffmpeg-ebur128-Filter.
    Gibt Lautheitswert und Dynamik als Tuple zurück.
    LUFS wird auf Basis der gesamten Datei berechnet.
    Benötigt ffmpeg im Systempfad.
    Liefert Werte wie z. B. (-13.7, 8.2)
    """
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
            return
        else:
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
    except subprocess.CalledProcessError as e:
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


# === Tagging-Funktionen ===

def set_tags(flac_path, tags, overwrite=True):
    """
    Setzt beliebige Tags (übergeben als dict) in einer FLAC-Datei.
    - Alle Keys werden zu Kleinbuchstaben normalisiert (FLAC/Mutagen-Standard).
    - Wenn overwrite=False, werden vorhandene Tags NICHT überschrieben.
    """
    audio = FLAC(flac_path)
    for tag, value in tags.items():
        tag = tag.lower()
        if overwrite or tag not in audio:
            audio[tag] = str(value)
    audio.save()


def get_tags(flac_path, tags=None):
    """
    Liest Tags aus einer FLAC-Datei.

    - Ohne tags:        Gibt alle Tags als dict zurück.
    - Mit String:       Gibt den Wert (oder None) für EIN Tag zurück.
    - Mit Liste/Tuple:  Gibt dict mit diesen Tags zurück (fehlende: None).
    Alle Keys werden zu Kleinbuchstaben normalisiert.
    """
    audio = FLAC(flac_path)
    all_tags = {k.lower(): v for k, v in dict(audio).items()}

    if tags is None:
        return all_tags

    if isinstance(tags, str):
        # Einzelner Tag
        return all_tags.get(tags.lower(), [None])[0]

    # Mehrere Tags als Liste/Tuple
    return {tag: all_tags.get(tag.lower(), [None])[0] for tag in tags}


def touch_comment_tag(flac_path):
    """
    Stellt sicher, dass ein Kommentar für FLAC-Dateien im Standardfeld 'COMMENT' steht.
    Kopiert ggf. den Inhalt aus 'description', entfernt dieses Feld danach und speichert die Datei.
    """
    flac_file = FLAC(flac_path)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()


def touch_padding(flac_path, size=8192):
    """
    Versucht, einen PADDING-Block der gegebenen Größe (default: 8192 Bytes) hinzuzufügen.
    Wenn bereits ein PADDING-Block vorhanden ist, tut die Funktion nichts.
    Ignoriert den Fehler, der durch vorhandenes Padding entsteht.
    """
    try:
        subprocess.run(
            ['metaflac', f'--add-padding={size}', str(flac_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        # Fehler beim Hinzufügen – vermutlich weil PADDING schon existiert
        pass
