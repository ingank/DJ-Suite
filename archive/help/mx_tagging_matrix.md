
# 🎛️ Track Tagging-System – Übersicht (Stand: Jetzt)

## 🧱 Tag-Matrix

| Tag           | RAW         | ARCHIV      | STAGE         | WORKSPACE     | BAG           | MAPPED TO (DJ-System)        | Bemerkung                                               |
|---------------|-------------|-------------|----------------|----------------|----------------|-------------------------------|----------------------------------------------------------|
| ARTIST        | ☐           | ☐           | ✅ Pflicht      | ✅              | ✅              | ✅ ARTIST                    | Identifikation                                           |
| TITLE         | ☐           | ☐           | ✅ Pflicht      | ✅              | ✅              | ✅ TITLE                     | Identifikation                                           |
| SUBTITLE      | ☐           | ☐           | ☐ optional      | ✅ optional     | ✅ optional     | ✅ MIXARTIST (optional)      | Version, Remix, Mixinfo – nur wenn relevant             |
| MX-ID         | ☐ optional  | ☐ optional  | ✅ erzeugt & fixiert | ✅ mitgeführt   | ✅ mitgeführt   | ❌ nicht gemappt              | SHA-256 des WAV-Audiostreams                            |
| MX-LUFS       | ☐           | ☐           | ✅ Datei-Wert   | ✅ Datei-Wert   | ✅ Datei-Wert   | ❌ nicht gemappt              | Messbarer Loudness-Wert                                 |
| MX-BPM        | ☐           | ☐           | ✅ Pflicht      | ✅              | ✅              | optional → BPM               | Hauptgeschwindigkeit des Tracks                          |
| MX-BPM-RANGE  | ☐           | ☐           | ☐ optional      | ✅ optional     | ✅ optional     | ❌ nicht gemappt              | Nur setzen bei relevanter BPM-Variation                 |
| MX-COMMENT    | ☐           | ☐           | ✅ optional     | ✅ optional     | ✅ optional     | ❌ nicht gemappt              | Technische Freitext-Anmerkung                           |
| MX-FLAG       | ☐           | ☐           | ✅ optional     | ✅ optional     | ✅ optional     | ❌ nicht gemappt              | Kurzcode zur Arbeitsanweisung / Beobachtung             |

## 🧭 Workflow-Stufen

| Phase       | Funktion                                                       | Format |
|-------------|----------------------------------------------------------------|--------|
| RAW         | Eingangspunkt für Material (WAV, ungetaggt, optional prüfbar) | WAV    |
| ARCHIV      | Geordnetes Backup & Referenz (ohne Pflicht-Tags)              | WAV    |
| STAGE       | Tagging beginnt, FLAC wird erzeugt, technische Analyse        | FLAC   |
| WORKSPACE   | Aktive Bearbeitung, Feedback, Rework                          | FLAC   |
| BAG         | Finalisierte, DJ-fähige Tracks                                | FLAC   |

## 📎 Beispiel `.txt` Companion-Datei

```
MX-ID: 8F271A...
MX-BPM: 130
MX-LUFS: -13.7
MX-COMMENT: Transienten unsauber, Snare etwas dumpf
MX-FLAG: transient-blur
ARTIST: Sonic Vale
TITLE: Static Bloom
SUBTITLE: Club Cut
```
