# lib/flac.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import json
import subprocess
from mutagen.flac import FLAC
from lib import config
from lib.utils import get_timestamp
from lib.utils import loudness as loudness_measure
from lib.hash import sha256 as hash_sha256

__all__ = [
    "set_tags",
    "get_tags",
    "touch_comment_tag",
    "encode",
]

# ---------- Tag-Helper (FLAC only) ----------


def set_tags(flac_path: Path, tags: Dict[str, Any], overwrite: bool = True) -> None:
    audio = FLAC(str(flac_path))
    for tag, value in tags.items():
        k = tag.lower()
        if overwrite or k not in audio:
            audio[k] = str(value)
    audio.save()


def get_tags(flac_path: Path, tags: Optional[Any] = None):
    audio = FLAC(str(flac_path))
    all_tags = {k.lower(): v for k, v in dict(audio).items()}
    if tags is None:
        return all_tags
    if isinstance(tags, str):
        return all_tags.get(tags.lower(), [None])[0]
    return {tag: all_tags.get(str(tag).lower(), [None])[0] for tag in tags}


def touch_comment_tag(flac_path: Path) -> None:
    flac_file = FLAC(str(flac_path))
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()

# ---------- ffmpeg/ffprobe helpers (keine try/except; Exit bei Fehler) ----------


def _run(cmd: list[str]) -> None:
    """Run external command; raise on non-zero (CLI fängt Exceptions)."""
    proc = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        # konsolidierte Fehlermeldung; keine weitere Behandlung hier
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")


def _ffprobe_json(path: Path) -> dict:
    """
    Führt ffprobe aus und gibt das Ergebnis als dict zurück.
    - JSON wird vollständig im RAM gehalten (stdout=PIPE).
    - stderr bleibt getrennt, um das JSON nicht zu verunreinigen.
    - Harte Fehlerbehandlung: non-zero returncode -> RuntimeError.
    """
    cmd = [
        "ffprobe",
        "-v", "error",          # nur echte Fehler
        "-hide_banner",         # kein Banner/Versionstext
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    proc = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed ({proc.returncode}) for {path}\n{proc.stderr}"
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        preview = (proc.stdout or "")[:500]
        raise RuntimeError(
            f"ffprobe JSON parse error: {e} for {path}\n"
            f"STDERR: {proc.stderr}\n"
            f"STDOUT preview (first 500B): {preview}"
        )


def _first_audio_stream(info: dict) -> Optional[dict]:
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return None


def _first_attached_pic_index(info: dict) -> Optional[int]:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            disp = s.get("disposition") or {}
            if disp.get("attached_pic") == 1:
                return s.get("index")
    return None

# --- Hauptfunktionen :: Audio-Transkodierungen ------------------


def encode(
    src_path: Path,
    out_path: Path,
    *,
    rel_source_path: Optional[str] = None,
    force_reencode: bool = False,   # wird für FLAC ignoriert
    keep_temp: bool = False,        # keine Tempfiles mehr; nur für API-Kompat.
) -> dict:
    """
    Blockweise Encode-Variante:
      - FLAC→FLAC: IMMER Stream-Copy (kein Reencode), Cover vereinheitlichen (600x600 MJPEG, attached_pic)
      - Nicht-FLAC: Reencode nach Policy aus config.KNOWN_* (lossy => s16 + shibata; lossless => flac)
      - Metadaten beibehalten (-map_metadata 0)
      - MX-Tags NACH dem ffmpeg-Run auf out_path schreiben
      - Danach COMMENT harmonisieren
    """
    src_path = Path(src_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Probe & Erkennung
    info = _ffprobe_json(src_path)
    a = _first_audio_stream(info)
    if not a:
        raise RuntimeError("Kein Audiostream im Eingang gefunden.")
    pic_index = _first_attached_pic_index(info)

    source_suffix = src_path.suffix.lower()
    is_flac = (source_suffix == ".flac")
    is_lossy_ext = source_suffix in config.KNOWN_LOSSY_AUDIO_EXTENSIONS

    # 2) ffmpeg-Aufruf (fallweise, ohne Command-Build)
    cover_source = "original" if pic_index is not None else "placeholder"
    ffmpeg_block = ""
    note = ""

    if is_flac:
        # FLAC → FLAC: NIE reencoden, force_reencode wird ignoriert
        if force_reencode:
            note = "force_reencode ignored for FLAC"

        if pic_index is not None:
            ffmpeg_block = "FLAC_REMUX_ORIG_COVER"
            _run([
                "ffmpeg", "-v", "error", "-i", str(src_path),
                "-map_metadata", "0",
                "-map", "0:a:0", "-map", f"0:{pic_index}",
                "-vf", "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600",
                "-disposition:v:0", "attached_pic",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-y", str(out_path)
            ])
        else:
            placeholder = Path(config.EMPTY_COVER)
            if not placeholder.exists():
                raise RuntimeError(
                    f"EMPTY_COVER nicht gefunden: {placeholder}")
            ffmpeg_block = "FLAC_REMUX_PLACEHOLDER"
            _run([
                "ffmpeg", "-v", "error",
                "-i", str(src_path), "-i", str(placeholder),
                "-map_metadata", "0",
                "-map", "0:a:0", "-map", "1:v:0",
                "-vf", "scale=600:600",
                "-disposition:v:0", "attached_pic",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-y", str(out_path)
            ])
        mode = "REMUX"

    else:
        # Nicht-FLAC → Reencode nach Extension-Policy
        if is_lossy_ext:
            if pic_index is not None:
                ffmpeg_block = "REENC_LOSSY_ORIG_COVER"
                _run([
                    "ffmpeg", "-v", "error", "-i", str(src_path),
                    "-map_metadata", "0",
                    "-map", "0:a:0", "-map", f"0:{pic_index}",
                    "-vf", "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600",
                    "-disposition:v:0", "attached_pic",
                    "-c:a", "flac", "-sample_fmt", "s16",
                    "-af", "aresample=resampler=soxr:dither_method=shibata",
                    "-c:v", "mjpeg",
                    "-y", str(out_path)
                ])
            else:
                placeholder = Path(config.EMPTY_COVER)
                if not placeholder.exists():
                    raise RuntimeError(
                        f"EMPTY_COVER nicht gefunden: {placeholder}")
                ffmpeg_block = "REENC_LOSSY_PLACEHOLDER"
                _run([
                    "ffmpeg", "-v", "error",
                    "-i", str(src_path), "-i", str(placeholder),
                    "-map_metadata", "0",
                    "-map", "0:a:0", "-map", "1:v:0",
                    "-vf", "scale=600:600",
                    "-disposition:v:0", "attached_pic",
                    "-c:a", "flac", "-sample_fmt", "s16",
                    "-af", "aresample=resampler=soxr:dither_method=shibata",
                    "-c:v", "mjpeg",
                    "-y", str(out_path)
                ])
            mode = "REENC_LOSSY"

        else:
            # lossless (oder unbekannt → konservativ als lossless behandeln)
            if pic_index is not None:
                ffmpeg_block = "REENC_LOSSLESS_ORIG_COVER"
                _run([
                    "ffmpeg", "-v", "error", "-i", str(src_path),
                    "-map_metadata", "0",
                    "-map", "0:a:0", "-map", f"0:{pic_index}",
                    "-vf", "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600",
                    "-disposition:v:0", "attached_pic",
                    "-c:a", "flac",
                    "-c:v", "mjpeg",
                    "-y", str(out_path)
                ])
            else:
                placeholder = Path(config.EMPTY_COVER)
                if not placeholder.exists():
                    raise RuntimeError(
                        f"EMPTY_COVER nicht gefunden: {placeholder}")
                ffmpeg_block = "REENC_LOSSLESS_PLACEHOLDER"
                _run([
                    "ffmpeg", "-v", "error",
                    "-i", str(src_path), "-i", str(placeholder),
                    "-map_metadata", "0",
                    "-map", "0:a:0", "-map", "1:v:0",
                    "-vf", "scale=600:600",
                    "-disposition:v:0", "attached_pic",
                    "-c:a", "flac",
                    "-c:v", "mjpeg",
                    "-y", str(out_path)
                ])
            mode = "REENC_LOSSLESS"

    # 3) Analyse auf dem fertigen Output + MX-Tags setzen
    lufs, lra = loudness_measure(out_path)
    mx_tags: Dict[str, Any] = {}
    if lufs is not None:
        mx_tags["MX-LUFS"] = f"{lufs:.2f}"
    if lra is not None:
        mx_tags["MX-LRA"] = f"{lra:.2f}"
    # Archiv→MX Signatur (bewusst Quelle)
    mx_tags["MX-HASH"] = hash_sha256(src_path)
    mx_tags["MX-STAGETIME"] = get_timestamp()
    if rel_source_path:
        mx_tags["MX-ORIGINAL"] = rel_source_path
    set_tags(out_path, mx_tags, overwrite=True)

    # 4) COMMENT harmonisieren
    touch_comment_tag(out_path)

    return {
        "out_path": str(out_path),
        "actions": {
            "source_format": source_suffix.lstrip("."),
            "mode": mode,
            "ffmpeg_block": ffmpeg_block,
            "audio_copy": (mode == "REMUX"),
            "cover_source": cover_source,
            "cover_size": "600x600",
            "cover_codec": "mjpeg",
            "metadata_copied": True,
            "comment_touched": True,
        },
        "notes": note,
    }


def remux(
    src_path: Path,
    out_path: Path,
    *,
    rel_source_path: Optional[str] = None,
    keep_temp: bool = False,  # nur für Signatur-Konsistenz; wird hier nicht genutzt
) -> dict:
    """
    FLAC → FLAC, leichtgewichtig:
      - Audio: Stream-Copy (kein Reencode)
      - Cover: genau 1 Bild, quadratisch, 600x600, als MJPEG attached_pic
      - Metadaten: von Quelle übernehmen
      - Danach: touch_comment_tag()

    Pfadwahl:
      1) Wenn Quelle bereits ein Bild hat:
         ffmpeg -i input.flac -map 0:a:0 -map 0:v:<idx> -vf "crop(...),scale=600:600" -c:a copy -c:v mjpeg -disposition:v:0 attached_pic output.flac
      2) Sonst:
         ffmpeg -i input.flac -i EMPTY_COVER -map 0:a:0 -map 1:v:0 -c:a copy -c:v mjpeg -disposition:v:0 attached_pic output.flac
    """
    src_path = Path(src_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 0) Validierung: Quelle muss FLAC mit Audio-Stream sein
    info = _ffprobe_json(src_path)
    a = _first_audio_stream(info)
    if not a:
        raise RuntimeError("Kein Audiostream im Eingang gefunden.")
    codec = (a.get("codec_name") or "").lower()
    if codec != "flac":
        raise RuntimeError(
            "Quelle ist kein FLAC – remux() erwartet FLAC→FLAC.")

    # 1) Cover-Erkennung (attached_pic vorhanden?)
    pic_index = _first_attached_pic_index(info)

    if pic_index is not None:
        # Pfad 1: vorhandenes Cover croppen + auf 600x600 skalieren und als attached_pic einbetten
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map_metadata", "0",
            "-map", "0:a:0",
            "-map", f"0:{pic_index}",
            "-vf", "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600",
            "-disposition:v:0", "attached_pic",
            "-c:a", "copy",
            "-c:v", "mjpeg",
            "-y", str(out_path)
        ])
        cover_source = "original"
    else:
        # Pfad 2: Platzhalter einbetten
        placeholder = Path(config.EMPTY_COVER)
        if not placeholder.exists():
            raise RuntimeError(f"EMPTY_COVER nicht gefunden: {placeholder}")
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-i", str(placeholder),
            "-map_metadata", "0",
            "-map", "0:a:0",
            "-map", "1:v:0",
            "-vf", "scale=600:600",
            "-disposition:v:0", "attached_pic",
            "-c:a", "copy",
            "-c:v", "mjpeg",
            "-y", str(out_path)
        ])
        cover_source = "placeholder"

    # 3) COMMENT-Tag harmonisieren
    touch_comment_tag(out_path)

    return {
        "out_path": str(out_path),
        "actions": {
            "mode": "REMUX",
            "audio_copy": True,
            "cover_source": cover_source,
            "cover_size": "600x600",
            "cover_codec": "mjpeg",
            "metadata_copied": True,
            "comment_touched": True,
        },
        "notes": "" if pic_index is not None else "Kein Original-Cover → Platzhalter verwendet.",
    }
