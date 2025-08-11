"""
lib/file.py

Zentrale Library für:
- Audio-Hashing (PCM-basiert, formatagnostisch)
- Loudness-Messung
- FLAC-Transkodierung / -Remux mit vollständiger Tag-Übernahme
- Tagging-Helfer (lesen/schreiben/touch_comment_tag)

NEU:
- transcode(src_path, out_path, *, force_reencode=False, keep_temp=False)
  Erzeugt aus einer beliebigen Quelle eine neue FLAC-Datei als „Kopie“:
  * FLAC→FLAC: Audiostream-Kopie (Remux), außer force_reencode=True
  * Nicht-FLAC→FLAC: Re-Encode (ohne DSP); MP3-Sonderfall: s16 + Original-SR
  * Alle Tags via -map_metadata 0
  * Genau ein Front-Cover (erstes Originalcover oder EMPTY_COVER)
  * Immer finaler Remux (copy)
  * Danach touch_comment_tag() auf der finalen Datei

Hinweis:
- Kein Einsatz von 'metaflac' oder 'flac.exe' in neuen Pfaden.
- Legacy-Funktionen, die diese Tools benötigen, sind unten klar markiert.
"""

from __future__ import annotations

from PIL import Image
import subprocess
import shutil
import re
import os
import json
from datetime import datetime
from pathlib import Path
from mutagen.flac import FLAC, Picture
from lib import config


# =====================================================================
# Hilfsfunktionen (allgemein)
# =====================================================================

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _run(cmd: list[str]) -> None:
    """
    Führt einen Prozess aus und bricht bei Fehler sofort ab (kein try/except).
    Gibt bei Fehlern die stderr des Subprozesses in der Exception mit aus.
    """
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{proc.stderr.decode('utf-8', 'ignore')}"
        )


def _ffprobe_json(src: Path) -> dict:
    """
    ffprobe-Aufruf, der Streams + Format als JSON zurückgibt.
    """
    out = subprocess.check_output([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(src)
    ])
    return json.loads(out.decode("utf-8"))


def _first_audio_stream(info: dict) -> dict | None:
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return None


def _first_attached_pic_index(info: dict) -> int | None:
    """
    Liefert den Stream-Index des ersten eingebetteten Covers (attached_pic), falls vorhanden.
    """
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") == 1:
            return s.get("index")
    return None


def _shrink_to_max_1024(png_path: Path) -> None:
    """Verkleinert ein PNG auf max. 1024x1024, ohne Hochskalierung."""
    img = Image.open(png_path)
    if img.width > 1024 or img.height > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
        img.save(png_path, format="PNG")


# =====================================================================
# Audioanalyse & Konvertierung (bestehende Utilities)
# =====================================================================


def loudness(file: Path) -> tuple[float | None, float | None]:
    """
    Misst LUFS und Loudness Range (LRA) mit ffmpeg-ebur128-Filter.
    Gibt Lautheitswert und Dynamik als Tuple zurück.
    LUFS wird auf Basis der gesamten Datei berechnet.
    Liefert Werte wie z. B. (-13.7, 8.2)
    """
    ffmpeg_cmd = [
        'ffmpeg', '-hide_banner', '-nostats',
        '-i', str(file),
        '-map', '0:a:0',
        '-af', 'ebur128',
        '-f', 'null', '-'
    ]
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


# =====================================================================
# Encodierung ins Stage-Format (Original Bit-Ttiefe, Original SR)
# =====================================================================

def transcode(
    src_path: Path,
    out_path: Path,
    *,
    force_reencode: bool = False,
    keep_temp: bool = False,
) -> dict:
    """
    Erzeugt aus einer Quelle eine neue FLAC-Datei:

    - FLAC→FLAC: reiner Remux (Audiostream-Kopie), außer force_reencode=True
    - Nicht-FLAC→FLAC: Re-Encode (ohne DSP); MP3-Sonderfall: s16 + Original-SR
    - Alle Tags via -map_metadata 0
    - Genau ein Front-Cover (erstes Originalcover oder EMPTY_COVER)
    - Immer finaler Remux (copy), danach touch_comment_tag()
    """
    src_path = Path(src_path)
    out_path = Path(out_path)

    # Arbeitsbereich unter TEMP_ROOT
    temp_root = Path(config.TEMP_ROOT) / f"transcode-{_timestamp()}"
    work_dir = temp_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) Analyse via ffprobe
    info = _ffprobe_json(src_path)
    audio_stream = _first_audio_stream(info)
    if not audio_stream:
        raise RuntimeError("Kein Audiostream im Eingang gefunden.")

    source_suffix = src_path.suffix.lower()
    is_src_flac = (source_suffix == ".flac")

    # 1a) Cover früh ermitteln/extrahieren
    pic_index = _first_attached_pic_index(info)
    if pic_index is not None:
        cover_png = work_dir / "cover.png"
        # ffmpeg: Cover extrahieren, Metadaten entfernen, NICHT skalieren
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map", f"0:{pic_index}",
            "-frames:v", "1",
            "-an", "-map_metadata", "-1",
            "-y", str(cover_png)
        ])
        # nur verkleinern, wenn nötig
        _shrink_to_max_1024(cover_png)
        cover_bytes = cover_png.read_bytes()
        cover_mime = "image/png"
    else:
        empty = Path(config.EMPTY_COVER)
        if not empty.exists():
            raise RuntimeError(f"EMPTY_COVER nicht gefunden: {empty}")
        cover_bytes = empty.read_bytes()
        cover_mime = "image/png"

    # 2) Audio-Erzeugung → Zwischen-FLAC (mit allen Tags via -map_metadata 0)
    intermediate = work_dir / "audio.intermediate.flac"
    if is_src_flac and not force_reencode:
        # reiner Remux inkl. Metadaten
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map_metadata", "0",
            "-map", "0",
            "-c:a", "copy",
            "-y", str(intermediate)
        ])
        mode = "copy"
    else:
        # Re-Encode zu FLAC, keine DSP; MP3-Sonderfall: s16 + Original-SR
        cmd = [
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map_metadata", "0",
            "-vn",
            "-c:a", "flac",
            "-af", "aresample=resampler=soxr:dither_method=shibata"
        ]
        if source_suffix == ".mp3":
            cmd += ["-sample_fmt", "s16"]

        cmd += ["-y", str(intermediate)]
        _run(cmd)
        mode = "reencode"

    # 3) Cover in Zwischen-FLAC konsolidieren: exakt 1 Front Cover
    fl = FLAC(str(intermediate))
    fl.clear_pictures()

    pic = Picture()
    pic.data = cover_bytes
    pic.mime = cover_mime
    pic.type = 3  # Front Cover
    pic.desc = "Front Cover"
    fl.add_picture(pic)
    fl.save()

    # 4) Finales Remux (immer) → Blockordnung & Padding „sauber“
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-v", "error",
        "-i", str(intermediate),
        "-map", "0",
        "-c:a", "copy",
        "-y", str(out_path)
    ])

    # 5) touch_comment_tag() auf finaler Datei
    touch_comment_tag(out_path)

    # 6) Cleanup
    if not keep_temp:
        shutil.rmtree(temp_root, ignore_errors=True)

    return {
        "out_path": str(out_path),
        "actions": {
            "source_format": source_suffix.lstrip("."),
            "mode": mode,
            "tags_copied": True,
            "cover_added": "original" if pic_index is not None else "placeholder",
            "remuxed": True,
            "comment_touched": True,
        },
        "notes": "" if pic_index is not None else "Kein Original-Cover, Platzhalter verwendet.",
    }


# =====================================================================
# Weitere Hilfen (bestehend/leicht angepasst)
# =====================================================================

def to_stage(src: Path, dst_flac: Path, flac_copy: bool = True) -> None:
    """
    (Legacy-Helfer) Transcodiert eine Audio-Datei zu FLAC.
    FLAC: kopiert, wenn flac_copy=True, sonst neu encodiert.
    MP3: 16 Bit + Dither, andere: soxr-Resampler (keine DSP-Änderungen).
    Hinweis: In neuen Flows wird 'transcode(...)' bevorzugt.
    """
    ext = os.path.splitext(src)[1].lower()

    if ext == ".flac" and flac_copy:
        shutil.copy2(src, dst_flac)
        return

    mp3_mode = (ext == ".mp3")
    ffmpeg_cmd = ['ffmpeg', '-y', '-i', str(src), '-c:a', 'flac']
    if mp3_mode:
        ffmpeg_cmd.extend([
            '-sample_fmt', 's16',
            '-af', 'aresample=resampler=soxr:dither_method=shibata'
        ])
    else:
        ffmpeg_cmd.extend(['-af', 'aresample=resampler=soxr'])
    ffmpeg_cmd.append(str(dst_flac))
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)


def to_bag(src_flac: Path, dst_flac: Path, src_lufs: float, target_lufs: float) -> None:
    """
    Transkodiert src_flac nach dst_flac, normalisiert auf target_lufs (in dB LUFS).
    Input FLAC, Output FLAC, interne Verarbeitung s32 @ 44.1 kHz.
    """
    lufs_diff = target_lufs - src_lufs
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(src_flac),
        '-af', f'volume={lufs_diff:.1f}dB,aresample=resampler=soxr',
        '-c:a', 'flac',
        '-sample_fmt', 's32',
        '-ar', '44100',
        str(dst_flac)
    ]
    subprocess.run(
        ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )


# =====================================================================
# Tagging: Lesen/Schreiben/Touch
# =====================================================================

def set_tags(flac_path: Path, tags: dict, overwrite: bool = True) -> None:
    """
    Setzt beliebige Tags (übergeben als dict) in einer FLAC-Datei.
    - Keys werden zu Kleinbuchstaben normalisiert (mutagen/FLAC-Usus).
    - Wenn overwrite=False, werden vorhandene Tags NICHT überschrieben.
    """
    audio = FLAC(str(flac_path))
    for tag, value in tags.items():
        k = tag.lower()
        if overwrite or k not in audio:
            audio[k] = str(value)
    audio.save()


def get_tags(flac_path: Path, tags=None):
    """
    Liest Tags aus einer FLAC-Datei.

    - Ohne tags:        Gibt alle Tags als dict zurück.
    - Mit String:       Gibt den Wert (oder None) für EIN Tag zurück.
    - Mit Liste/Tuple:  Gibt dict mit diesen Tags zurück (fehlende: None).
    """
    audio = FLAC(str(flac_path))
    all_tags = {k.lower(): v for k, v in dict(audio).items()}

    if tags is None:
        return all_tags

    if isinstance(tags, str):
        return all_tags.get(tags.lower(), [None])[0]

    return {tag: all_tags.get(tag.lower(), [None])[0] for tag in tags}


def touch_comment_tag(flac_path: Path) -> None:
    """
    Stellt sicher, dass ein Kommentar im Standardfeld 'COMMENT' steht.
    Kopiert ggf. den Inhalt aus 'description', entfernt dieses Feld danach.
    """
    flac_file = FLAC(str(flac_path))
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()


# =====================================================================
# Legacy (vermeiden, da externe Tools flac/metaflac) – belassen für Rückwärtskompat.
# =====================================================================

def renew_flac(file: Path, padding: int = 65536) -> Path:
    """
    LEGACY: Erzeugt <file>.new via 'flac' (mit Padding) und führt touch_comment_tag() darauf aus.
    Beibehalten für Alt-Workflows, aber in neuen Pfaden NICHT verwenden.
    """
    if not file.is_file() or file.suffix.lower() != ".flac":
        raise ValueError(f"Ungültige Datei: {file}")

    new_file = file.with_suffix(".flac.new")

    subprocess.run(
        ["flac", "--force", "--padding",
            str(padding), "-o", str(new_file), str(file)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    touch_comment_tag(new_file)
    return new_file


def touch_padding(flac_path: Path, size: int = 8192) -> None:
    """
    LEGACY: Versucht, via 'metaflac' einen PADDING-Block hinzuzufügen.
    In neuen Workflows NICHT verwenden (ffmpeg-Remux liefert praxistaugliches Padding).
    """
    subprocess.run(
        ['metaflac', f'--add-padding={size}', str(flac_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
