# lib/utils.py

import os
import re
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime
from lib.config import AUDIO_EXTENSIONS


def get_timestamp():
    """
    Gibt einen aktuellen Zeitstempel als String im Format YYYY-mm-dd_HH-MM-SS zurück.
    Beispiel: 2024-07-17_19-35-01
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def make_filename(
    prefix: str,
    ext: str = "txt",
    suffix: Optional[str] = None,
    dir: Optional[str] = None,
    timestamp_format: str = "%Y%m%d-%H%M%S"
) -> Path:
    """
    Erstellt einen Dateinamen wie <prefix>-<timestamp>[-<suffix>].<ext>
    Optional im Verzeichnis dir.
    Beispiel: make_filename("hash-match") -> Path('hash-match-20240723-213350.txt')
    """
    ts = datetime.now().strftime(timestamp_format)
    name = f"{prefix}-{ts}"
    if suffix:
        name += f"-{suffix}"
    name += f".{ext.lstrip('.')}"
    if dir:
        return Path(dir) / name
    return Path(name)


def find_audio_files(root, absolute: bool = False, depth: Optional[int] = None, filter_ext=None):
    """
    Gibt eine LISTE aller Audiodateien (Snapshot) unterhalb von root zurück.
    - Standard: RELATIVE Pfade (absolute=False)
    - depth: maximale Verzeichnistiefe (None = unbegrenzt)
    - filter_ext: Liste erlaubter Endungen (z. B. [".flac", ".mp3"]), sonst AUDIO_EXTENSIONS
    """
    root = Path(root).resolve()
    root_depth = len(root.parts)
    filter_set = set(ext.lower() for ext in (filter_ext or AUDIO_EXTENSIONS))

    results = []
    for dirpath, _, filenames in os.walk(root):
        curr_depth = len(Path(dirpath).parts) - root_depth
        if depth is not None and curr_depth > depth:
            continue
        for name in filenames:
            file = (Path(dirpath) / name).resolve()
            if file.suffix.lower() in filter_set:
                results.append(file if absolute else file.relative_to(root))
    return results


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


def collect_audio_stats(root=".", extensions=None, depth=None, absolute=False, all_folders=False):
    """
    Zählt Audiodateien unterhalb von `root` in einem eigenen os.walk-Durchlauf.

    Args:
        root (str | Path): Startverzeichnis.
        extensions (Iterable[str] | None): erlaubte Suffixe (inkl. führendem Punkt).
            Default: lib.config.KNOWN_AUDIO_EXTENSIONS.
        depth (int | None): maximale Tiefe relativ zu `root` (None = unbegrenzt).
        absolute (bool): True = absolute Pfade in den Ergebnissen/Listen, sonst relative.
        all_folders (bool): Wenn True, enthält per_folder auch Ordner mit 0 Treffern (bis depth).

    Returns:
        dict: {
            "total": int,
            "per_ext": dict[str, int],
            "per_folder": dict[str, int],
            "duplicates": dict[str, list[str]],
        }
    """
    from lib.config import KNOWN_AUDIO_EXTENSIONS  # lazy import

    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Startverzeichnis nicht gefunden: {root}")

    # Ext-Menge normalisieren
    exts = set(extensions or KNOWN_AUDIO_EXTENSIONS)
    exts = {(e if str(e).startswith('.') else f'.{e}').lower() for e in exts}

    total = 0
    per_ext: dict[str, int] = {}
    per_folder: dict[str, int] = {}
    name_map: dict[str, list[str]] = {}

    root_depth = len(root.parts)
    seen_dirs: set[Path] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        curr_depth = len(Path(dirpath).parts) - root_depth
        if depth is not None and curr_depth > depth:
            dirnames[:] = []  # Abstieg stoppen
            continue

        dpath = Path(dirpath)
        seen_dirs.add(dpath)

        for name in filenames:
            p = dpath / name
            suffix = p.suffix.lower()
            if suffix not in exts:
                continue

            total += 1
            per_ext[suffix] = per_ext.get(suffix, 0) + 1

            folder_key_path = p.parent
            if absolute:
                folder_key = str(folder_key_path)
            else:
                folder_key = str(folder_key_path.relative_to(
                    root)) if folder_key_path != root else "."

            per_folder[folder_key] = per_folder.get(folder_key, 0) + 1

            stem_key = p.stem.casefold()
            path_str = str(p) if absolute else str(p.relative_to(root))
            name_map.setdefault(stem_key, []).append(path_str)

    if all_folders:
        for d in seen_dirs:
            if absolute:
                k = str(d)
            else:
                k = str(d.relative_to(root)) if d != root else "."
            per_folder.setdefault(k, 0)

    duplicates = {k: v for k, v in name_map.items() if len(v) > 1}

    return {
        "total": total,
        "per_ext": dict(sorted(per_ext.items(), key=lambda kv: (-kv[1], kv[0]))),
        "per_folder": dict(sorted(per_folder.items(), key=lambda kv: kv[0])),
        "duplicates": dict(sorted(duplicates.items(), key=lambda kv: kv[0])),
    }
