# lib/flac.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import json
import subprocess
import shutil
from mutagen.flac import FLAC, Picture

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

# ---------- vorhandene Tag-Helper (wie besprochen) ----------


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


def _source_is_lossy(codec: str) -> bool:
    # konservative Heuristik (ffprobe codec_name)
    lossy = {
        "mp3", "aac", "ac3", "eac3", "dts", "vorbis", "opus",
        "wma", "wmapro", "wmavoice", "nellymoser", "atrac1", "atrac3", "atrac3plus", "twinvq", "qdm2", "qdmc", "sbc"
    }
    return codec.lower() in lossy


def _source_is_lossless(codec: str) -> bool:
    lossless = {
        "flac", "alac", "wavpack", "tta", "tak", "shorten", "mlp", "truehd",
        # pcm_* gilt als lossless, eigene Behandlung über sample_fmt
    }
    c = codec.lower()
    return c in lossless or c.startswith("pcm_")


def _needs_downbit_to_s24(sample_fmt: Optional[str]) -> bool:
    if not sample_fmt:
        return False
    f = sample_fmt.lower()
    # float/double & 32-bit int → auf 24-bit int runter
    return f.startswith("flt") or f.startswith("dbl") or f.startswith("s32")

# ---------- Cover-Extraktion (PNG ≤1024) via ffmpeg ----------


def _extract_cover_png(src_path: Path, work_dir: Path, pic_index: Optional[int]) -> Tuple[bytes, str]:
    out_png = work_dir / "cover.png"
    if pic_index is not None:
        # skaliert IMMER down auf <=1024 (force_original_aspect_ratio=decrease), kein Upscale
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map", f"0:{pic_index}",
            "-frames:v", "1",
            "-vf", "scale='min(iw,1024)':'min(ih,1024)':force_original_aspect_ratio=decrease",
            "-an", "-map_metadata", "-1",
            "-y", str(out_png)
        ])
        return out_png.read_bytes(), "image/png"
    # Platzhalter
    empty = Path(config.EMPTY_COVER)
    if not empty.exists():
        raise RuntimeError(f"EMPTY_COVER nicht gefunden: {empty}")
    # optional: auch hier Downsizing via ffmpeg (konsequent), aber meist unnötig
    return empty.read_bytes(), "image/png"

# ---------- Hauptfunktion: 2-Stufen-Build ----------


def encode(
    src_path: Path,
    out_path: Path,
    *,
    rel_source_path: Optional[str] = None,
    force_reencode: bool = False,
    keep_temp: bool = False,
) -> dict:
    """
    Archiv → Stage-FLAC (2 Stufen):
      1) Zwischen-FLAC bauen (copy oder encode) + Cover einbetten + MX-Tags (inkl. LUFS/LRA/HASH)
      2) Finaler Remux (copy) für stabile Block-/Padding-Struktur
      3) touch_comment_tag() nur auf finaler Datei
    """
    src_path = Path(src_path)
    out_path = Path(out_path)

    # temp-Arbeitsbereich
    temp_root = Path(config.TEMP_ROOT) / f"flac-encode-{get_timestamp()}"
    work_dir = temp_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) Probe
    info = _ffprobe_json(src_path)
    a = _first_audio_stream(info)
    if not a:
        raise RuntimeError("Kein Audiostream im Eingang gefunden.")
    codec = (a.get("codec_name") or "").lower()
    sample_fmt = (a.get("sample_fmt") or "").lower()
    source_suffix = src_path.suffix.lower()
    is_src_flac = (source_suffix == ".flac")

    # 2) Cover vorbereiten
    pic_index = _first_attached_pic_index(info)
    cover_bytes, cover_mime = _extract_cover_png(src_path, work_dir, pic_index)

    # 3) Zwischen-FLAC erzeugen (immer)
    intermediate = work_dir / "audio.intermediate.flac"
    if is_src_flac and not force_reencode and not _needs_downbit_to_s24(sample_fmt):
        # FLAC → FLAC: reiner Remux (Audio-only), Metadaten übernehmen
        _run([
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map_metadata", "0",
            "-map", "0:a:0",
            "-c:a", "copy",
            "-vn", "-sn",
            "-y", str(intermediate)
        ])
        mode = "REMUX"
    else:
        # Re-encode nach Policy
        cmd = [
            "ffmpeg", "-v", "error",
            "-i", str(src_path),
            "-map_metadata", "0",
            "-map", "0:a:0",
            "-vn", "-sn",
            "-c:a", "flac",
        ]

        # Für ALLE lossy-Codecs: s16 + Shibata-Dither (SR unverändert)
        if _source_is_lossy(codec):
            cmd += ["-sample_fmt", "s16",
                    "-af", "aresample=resampler=soxr:dither_method=shibata"]

        # Sonst: nichts weiter setzen – FFmpeg wählt das sinnvolle Zielformat selbst
        cmd += ["-y", str(intermediate)]
        _run(cmd)
        mode = "REENC"

    # 3b) Cover in intermediate einbetten (genau 1 Front Cover)
    fl = FLAC(str(intermediate))
    fl.clear_pictures()
    pic = Picture()
    pic.data = cover_bytes
    pic.mime = cover_mime
    pic.type = 3  # Front Cover
    pic.desc = "Front Cover"
    fl.add_picture(pic)
    fl.save()

    # 4) Analyse am intermediate: LUFS/LRA + HASH
    lufs, lra = loudness_measure(intermediate)
    mx_tags: Dict[str, Any] = {}
    if lufs is not None:
        mx_tags["MX-LUFS"] = f"{lufs:.2f}"
    if lra is not None:
        mx_tags["MX-LRA"] = f"{lra:.2f}"
    # Hash über Originalsignal (src_path); Details kapselt lib.hash.sha256()
    mx_tags["MX-HASH"] = hash_sha256(src_path)
    # Herkunft / Zeit
    mx_tags["MX-EXTENSION"] = source_suffix.lstrip(".").upper()
    mx_tags["MX-STAGETIME"] = get_timestamp()
    if rel_source_path:
        mx_tags["MX-ORIGINAL"] = rel_source_path
    if mx_tags:
        set_tags(intermediate, mx_tags, overwrite=True)

    # 5) Finaler Remux (immer) → stabile Blöcke/Padding
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-v", "error",
        "-i", str(intermediate),
        "-c:a", "copy",
        "-y", str(out_path)
    ])

    # 6) Nur jetzt: COMMENT-Tag harmonisieren
    touch_comment_tag(out_path)

    # 7) Cleanup
    result_note = "" if pic_index is not None else "Kein Original-Cover, Platzhalter verwendet."
    if not keep_temp:
        shutil.rmtree(temp_root, ignore_errors=True)

    return {
        "out_path": str(out_path),
        "actions": {
            "source_format": source_suffix.lstrip("."),
            "mode": mode,
            "tags_copied": True,
            "cover_added": "original" if pic_index is not None else "placeholder",
            "intermediate_tags": list(mx_tags.keys()),
            "final_remux": True,
            "comment_touched": True,
        },
        "notes": result_note,
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
