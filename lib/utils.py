# lib/utils.py

from typing import Optional
from pathlib import Path
import os
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
