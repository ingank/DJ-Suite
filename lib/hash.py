# lib/hash.py

import subprocess
import hashlib
from typing import Iterator, Tuple, Optional, Dict, List, Set
from collections import defaultdict
from pathlib import Path
from lib.utils import find_audio_files


def read(filepath: str) -> Iterator[Tuple[str, str]]:
    """
    Liest eine Hashdatei im Format <hash> <path>.
    - Nur die letzte Zeile darf leer sein (wird ignoriert).
    - Fehlerhafte Zeilen oder leere Zeilen (außer am Dateiende) führen zum Abbruch (Exception).
    - Gibt (hash, path) pro Zeile zurück.
    """
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()
    n = len(lines)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            # Nur die letzte Zeile darf leer sein!
            if i == n - 1:
                continue
            raise ValueError(
                f"Leere Zeile {i+1} (nicht am Dateiende) in {filepath!r}")
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(
                f"Fehlerhafte Zeile {i+1} in {filepath!r}: {line!r}")
        yield parts[0], parts[1]


def write(filepath: str, items: Iterator[Tuple[str, str]]) -> Iterator[str]:
    """
    Schreibt eine Folge von (hash, path)-Tupeln in die Datei filepath.
    - Bricht mit Exception ab, wenn die Datei bereits existiert (kein Überschreiben).
    - Eine Zeile pro Paar: <hash> <path>.
    - Gibt jede Zeile beim Schreiben als String zurück (Generator).
    """
    pfad = Path(filepath)
    if pfad.exists():
        raise FileExistsError(f"Datei existiert bereits: {filepath}")
    with pfad.open("w", encoding="utf-8") as f:
        for hashval, relpath in items:
            line = f"{hashval} {relpath}"
            f.write(line + "\n")
            yield line  # Generator: Zeile auch zurückgeben


def scan(directory: str, depth: Optional[int] = None) -> Iterator[Tuple[str, str]]:
    """
    Findet alle unterstützten Audiodateien im Verzeichnis (rekursiv, optional bis zu gegebener Tiefe),
    berechnet SHA256-Hashes und gibt (hash, relpath) für jede Datei zurück.
    """
    root = Path(directory).resolve()
    # Achtung: find_audio_files gibt RELATIVE Pfade, wenn absolute=False
    for relpath in find_audio_files(root, absolute=False, depth=depth):
        hashval = sha256(root / relpath)
        yield hashval, relpath.as_posix()


def dupes(items: Iterator[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Liefert ein Dict aller Hashes, die mehrfach vorkommen,
    zusammen mit allen zugehörigen Pfaden:
      {hash: [pfad1, pfad2, ...], ...}
    Nur Hashes mit mehr als einem Pfad werden geliefert!
    """
    hash_to_paths = defaultdict(list)
    for hashval, path in items:
        hash_to_paths[hashval].append(path)
    return {h: ps for h, ps in hash_to_paths.items() if len(ps) > 1}


def match(
    source1: Iterator[Tuple[str, str]],
    source2: Iterator[Tuple[str, str]]
) -> Iterator[Tuple[str, str]]:
    """
    Gibt alle (hash, path) aus source1 zurück, deren hash auch in source2 vorkommt.
    Reihenfolge bleibt wie in source1. In-File-Dubletten werden geliefert.
    """
    hashes2: Set[str] = set(hashval for hashval, _ in source2)
    for hashval, path1 in source1:
        if hashval in hashes2:
            yield hashval, path1


def diff(
    source1: Iterator[Tuple[str, str]],
    source2: Iterator[Tuple[str, str]]
) -> Iterator[Tuple[str, str]]:
    """
    Gibt alle (hash, path) aus source1 zurück, deren Hash NICHT in source2 vorkommt.
    Reihenfolge bleibt wie in source1. In-File-Dubletten werden geliefert.
    """
    hashes2: Set[str] = set(hashval for hashval, _ in source2)
    for hashval, path1 in source1:
        if hashval not in hashes2:
            yield hashval, path1


def sort_by_path(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Gibt eine neue Liste zurück, sortiert nur nach Pfad (aufsteigend).
    """
    return sorted(items, key=lambda t: t[1].lower())


def sort_by_hash_path(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Gibt eine neue Liste zurück, sortiert erst nach Hash, dann nach Pfad (beides aufsteigend).
    """
    return sorted(items, key=lambda t: (t[0], t[1]))


def sha256(file: Path) -> str:
    # Neu aus lib.file hierher verschoben
    """
    Berechnet den SHA-256-Hash des Audiostreams einer Datei.
    Verwendet PCM 24bit/96kHz Stereo als normiertes Zwischenformat.
    Eingabeformat ist flexibel (z. B. MP3, FLAC, WAV).
    Gibt hexadezimale Hash-Zeichenkette zurück.
    """
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(file),
        '-map', '0:a:0',
        '-vn', '-acodec', 'pcm_s24le', '-ar', '96000', '-ac', '2',
        '-f', 's24le', '-'
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    hasher = hashlib.sha256()
    while True:
        chunk = proc.stdout.read(1024 * 1024)
        if not chunk:
            break
        hasher.update(chunk)
    proc.wait()
    return hasher.hexdigest()
