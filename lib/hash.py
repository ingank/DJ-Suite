# lib/hash.py

from typing import Iterator, Tuple, Optional
from pathlib import Path
from lib.soundfile import sha256
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


def write(filepath: str, items: Iterator[Tuple[str, str]]) -> None:
    """
    Schreibt eine Folge von (hash, path)-Tupeln in die Datei filepath.
    - Bricht mit Exception ab, wenn die Datei bereits existiert (kein Überschreiben).
    - Eine Zeile pro Paar: <hash> <path>.
    """
    pfad = Path(filepath)
    if pfad.exists():
        raise FileExistsError(f"Datei existiert bereits: {filepath}")
    with pfad.open("w", encoding="utf-8") as f:
        for hashval, relpath in items:
            f.write(f"{hashval} {relpath}\n")


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


def compare(
    source1: Iterator[Tuple[str, str]],
    source2: Iterator[Tuple[str, str]]
) -> Iterator[Tuple[str, Optional[str], Optional[str]]]:
    """
    Vergleicht zwei Folgen von (hash, path)-Tupeln.
    Gibt für jeden Hash alle Paarungen (hash, path1, path2) zurück:
      - Nur in 1: (hash, path1, None)
      - Nur in 2: (hash, None, path2)
      - In beiden: alle Kombinationen (bei Duplikaten)
    """
    pass
