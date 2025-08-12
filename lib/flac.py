# lib/flac.py
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from mutagen.flac import FLAC

__all__ = [
    "set_tags",
    "get_tags",
    "touch_comment_tag",
]

def set_tags(flac_path: Path, tags: Dict[str, Any], overwrite: bool = True) -> None:
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


def get_tags(flac_path: Path, tags: Optional[Union[str, Iterable[str]]] = None):
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

    return {tag: all_tags.get(str(tag).lower(), [None])[0] for tag in tags}


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
