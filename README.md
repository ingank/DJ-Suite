# DJ Suite

Eine kleine Sammlung von Python-CLI-Tools für das Kuratieren von Audiodateien (z. B. FLAC/MP3) in DJ‑Workflows.

## Was ist drin?
- `count.py` — zählt Audiodateien in einem Ordnerbaum und erzeugt einfache Statistiken.
- `hash.py` — erstellt/prüft Datei‑Hashes zur Integritätskontrolle.
- `loudness.py` — analysiert die Lautheit von Audiodateien und protokolliert Ergebnisse.
- `transcode.py` — transkodiert Audiodateien gemäß Konfiguration (z. B. FLAC → MP3/AAC).
- `lib/` — Hilfsfunktionen (Datei‑/FLAC‑Handling, Hashing, Utilities).
- `archive/` — ältere/zusätzliche Tools und Hilfedateien.
- `djs-config.sample.yaml` — Beispiel‑Konfiguration.

## Voraussetzungen
- Python 3.10+
- FFmpeg im PATH (für `transcode.py`)
- Optional: `metaflac` für FLAC‑Tags


## Verwendung (Kurzform)
> Die Skripte sind eigenständige CLI‑Tools. Optionen können je nach Version variieren – `--help` zeigt Details.

```bash
# Dateien zählen
python count.py /pfad/zur/musik

# Lautheit analysieren (Beispiel)
python loudness.py /pfad/zur/musik

# Transkodieren mit Konfigurationsdatei
python transcode.py --config djs-config.yaml --input /pfad/in --output /pfad/out

# Hashes erzeugen oder prüfen (Beispiele)
python hash.py --write sha256 *.flac
python hash.py --verify hashes.txt
```

## Konfiguration
Kopiere `djs-config.sample.yaml` zu `djs-config.yaml` und passe Pfade/Presets an.

## Lizenz
Siehe `LICENSE`.
