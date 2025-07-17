# DJ-Suite

Die DJ-Suite organisiert und automatisiert die Verwaltung deiner Musikbibliothek  
vom Archiv über Arbeitskopien bis zum einsatzbereiten DJ-System.

## Bereiche der DJ-Suite

### 1. Archiv (GEN0)
- Enthält die **Originaldateien** aller Tracks, sauber archiviert und unverändert.
- Dateien liegen typischerweise in ZIP-Archiven unterteilt nach Quellen oder Labels.
- Keine Bearbeitung, keine Konvertierung – dient als „Master“-Ablage.

### 2. Stage (GEN1)
- Hier landen **FLAC-Kopien der Originale** in ihrer jeweiligen Bittiefe und Samplingrate.
- Die Tracks werden einem **Dateibaum nach GENRES** zugeordnet (z. B. /House/Deep House/…).
- Dient als Arbeitsbereich für Selektion, Tagging und Vorhören.

### 3. Engine Base (GEN2)
- Enthält die für **Engine DJ Desktop und Engine DJ OS** vorbereiteten Files:
  - **FLAC, 24 Bit / 44.1 kHz**
  - Dateiname ist der SHA256-Hash des GEN0-Inhalts: `<SHA256>.flac`
  - **Flache Hierarchie** für problemlosen Import in Engine DJ
  - Optimiert für schnelles und sicheres Importieren und Re-Importieren

---

Weitere Infos und Workflows folgen!
