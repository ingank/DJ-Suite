# lib/hash.py

from typing import Iterator, Tuple, Optional

def read(filepath: str) -> Iterator[Tuple[str, str]]:
    """
    Liest eine Hashdatei im Format <hash> <path>.
    - Nur die letzte Zeile darf leer sein (wird ignoriert).
    - Fehlerhafte Zeilen oder leere Zeilen (außer am Dateiende) führen zum Abbruch (Exception).
    - Gibt (hash, path) pro Zeile zurück.
    """
    pass


def write(filepath: str, items: Iterator[Tuple[str, str]]) -> None:
    """
    Schreibt eine Folge von (hash, path)-Tupeln in die Datei filepath.
    - Bricht mit Exception ab, wenn die Datei bereits existiert (kein Überschreiben).
    - Eine Zeile pro Paar: <hash> <path>.
    """
    pass


def scan(directory: str, depth: Optional[int] = None) -> Iterator[Tuple[str, str]]:
    """
    Findet alle unterstützten Audiodateien im Verzeichnis (rekursiv, optional bis zu gegebener Tiefe),
    berechnet SHA256-Hashes und gibt (hash, relpath) für jede Datei zurück.
    """
    pass


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
