# lib/utils.py

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


def find_audio_files(root, absolute=False):
    """
    Generator: Gibt alle Audiodateien (laut config.py) unterhalb von root zurück.
    Standardmäßig RELATIVE Pfade (absolute=False).
    Wenn absolute=True, gibt die Funktion absolute Pfade zurück.
    """
    root = Path(root).resolve()
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            file = (Path(dirpath) / name).resolve()
            if file.suffix.lower() in AUDIO_EXTENSIONS:
                yield file if absolute else file.relative_to(root)
