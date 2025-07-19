# lib/tagging.py

from mutagen.flac import FLAC


def touch_comment(file):
    """
    Kopiert den Tag 'description' (falls vorhanden) ins FLAC-Standardfeld 'COMMENT'.
    Entfernt 'description' danach. Sichert FLAC-Kompatibilität für Kommentar-Tags.
    """
    flac_file = FLAC(file)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()
        print(f"[OK] Kommentar-Tag korrigiert in: {file}")


def set_tags(flac_path, sha256=None, gen0_format=None, **extra_tags):
    """
    Setzt FLAC-Tags:
      - GEN0-SHA256: Hash-Wert (direkt übergeben)
      - GEN0-FORMAT: Ursprungsformat (direkt übergeben, z.B. 'WAV', 'MP3')
      - Beliebige weitere Tags als Schlüsselwort-Argumente
    """
    audio = FLAC(flac_path)
    if sha256:
        audio["GEN0-SHA256"] = sha256
    if gen0_format:
        audio["GEN0-FORMAT"] = gen0_format
    # Zusätzliche Tags setzen
    for tag, value in extra_tags.items():
        audio[tag] = str(value)
    audio.save()
    print(f"[OK] Tags gesetzt für: {flac_path}")
