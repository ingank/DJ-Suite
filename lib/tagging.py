"""
tagging.py

FLAC-Tagging-Toolkit für Mutagen

Bietet komfortable Funktionen zum Lesen, Setzen und Anpassen von Tags in FLAC-Dateien.
- Tags werden standardmäßig immer als Kleinbuchstaben behandelt (Mutagen/Vorbis-Standard).
- Ermöglicht flexibles Setzen einzelner oder mehrerer Tags, mit Overwrite-Option.
- Komfortables Auslesen einzelner oder mehrerer Tags; Rückgabe als String, Dict oder vollständige Tag-Übersicht.
- Spezialfunktion für die FLAC-Kompatibilität: Kopiert "description" ins Standardfeld "COMMENT".

Voraussetzung: mutagen >= 1.44

Empfohlen für Audio-Archive, DJ-Workflows und jede automatisierte FLAC-Tag-Verarbeitung.

Autor: (dein Name)
Lizenz: MIT (oder was du bevorzugst)
"""


from mutagen.flac import FLAC


def touch_comment(flac_path):
    """
    Stellt sicher, dass ein Kommentar für FLAC-Dateien im Standardfeld 'COMMENT' steht.
    Kopiert ggf. den Inhalt aus 'description', entfernt dieses Feld danach und speichert die Datei.
    """
    flac_file = FLAC(flac_path)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()


def set_tags(flac_path, tags, overwrite=True):
    """
    Setzt beliebige Tags (übergeben als dict) in einer FLAC-Datei.
    - Alle Keys werden zu Kleinbuchstaben normalisiert (FLAC/Mutagen-Standard).
    - Wenn overwrite=False, werden vorhandene Tags NICHT überschrieben.
    """
    audio = FLAC(flac_path)
    for tag, value in tags.items():
        tag = tag.lower()
        if overwrite or tag not in audio:
            audio[tag] = str(value)
    audio.save()


def get_tags(flac_path, tags=None):
    """
    Liest Tags aus einer FLAC-Datei.

    - Ohne tags:        Gibt alle Tags als dict zurück.
    - Mit String:       Gibt den Wert (oder None) für EIN Tag zurück.
    - Mit Liste/Tuple:  Gibt dict mit diesen Tags zurück (fehlende: None).
    Alle Keys werden zu Kleinbuchstaben normalisiert.
    """
    audio = FLAC(flac_path)
    all_tags = {k.lower(): v for k, v in dict(audio).items()}

    if tags is None:
        return all_tags

    if isinstance(tags, str):
        # Einzelner Tag
        return all_tags.get(tags.lower(), [None])[0]

    # Mehrere Tags als Liste/Tuple
    return {tag: all_tags.get(tag.lower(), [None])[0] for tag in tags}
