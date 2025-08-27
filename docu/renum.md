# renum.py – Detaillierte Beschreibung (Windows-Edition)

**renum.py** ist ein reines **Windows**-Kommandozeilentool zum massenhaften Umbenennen (Renummerieren) von Ordnern **oder** Dateien nach einem festen Schema. Es arbeitet transaktional (alles-oder-nichts), prüft Konflikte im Voraus und gibt alle Pfade im **Windows-Format** mit Backslashes aus (z. B. `.\foo\bar`).

> **Wichtig:** renum.py ist ausschließlich für **Microsoft Windows** entwickelt und läuft nicht unter POSIX/macOS/Linux.

---

## TL;DR – Schnellstart

```powershell
# Nur planen (keine Änderungen)
python renum.py folders . --dry-run

# Ordner rekursiv wirklich umbenennen
python renum.py folders . --recursive --go --start 0 --step 10 --width 3

# Dateien mit bestimmten Endungen planen
python renum.py files . --ext ".jpg,.png" --dry-run
```

* Standardmodus ist „planen“ (wenn `--go` fehlt, wird **nichts** geändert).
* Versteckte/System-Einträge und Symlinks/Junctions werden ignoriert.
* Parallele Läufe werden durch ein Lock-Verzeichnis (`.renum.lock`) verhindert.

---

## Zweck & Grundprinzip

renum.py vergibt für jeden Eintrag eine neue führende Nummer und formt den Namen so um:

* **Ordner:** `"<ZAHL> RESTNAME"`
* **Dateien:** `"<ZAHL> RESTNAME.ext"` (Dateiendung bleibt erhalten)

Die Zahl ist null-gefüllt (konfigurierbare Breite). Bereits vorhandene numerische Präfixe werden erkannt und durch das neue Präfix ersetzt. Mehrfach-Leerzeichen werden reduziert, Namen in **Unicode NFC** normalisiert.

---

## Plattform & Verhalten

* **Nur Windows:** Das Skript beendet sich sofort mit Fehlercode, wenn es nicht auf Windows läuft.
* **Windows-Sortierung:** Case-insensitive, locale-basiert, stabil – ähnlich `dir` unter Windows.
* **Pfadausgabe:** Relative Pfade mit Backslashes (z. B. `.\A\B`).

---

## CLI-Überblick

### Subkommandos

* `folders [PATH]` – Ordner umbenennen (optional **rekursiv** mit globaler Nummernfolge in Preorder)
* `files [PATH]` – Dateien umbenennen (**nie rekursiv**), optional mit Endungsfilter

`PATH` ist das Zielverzeichnis (Standard: `.`). In beiden Modi gilt: Wenn `--go` fehlt, wird nur ein **Dry-Run** ausgegeben.

### Gemeinsame Optionen

* `--start N` – Startwert der Nummerierung (Standard: `0`)
* `--step N` – Schrittweite (Standard: `10`)
* `--width N` – Stellenanzahl (Zero-Padding, Standard: `3`)
* `--dry-run` – Nur planen/anzeigen, nichts ändern
* `--go` – Änderungen wirklich durchführen
* `--verbose` – Ausführliche Logs (auf **stderr**)

### Modusspezifische Optionen

* `folders`:

  * `--recursive` – rekursive Nummerierung (eine **globale** Sequenz für den gesamten Baum; Preorder)
* `files`:

  * `--ext ".jpg,.png"` – optionale Kommaliste von Endungen (case-insensitiv); ohne Punkt wird automatisch `.` vorangestellt

---

## Erkennung & Umbau der Namen

* **Präfixerkennung:** Ein führender Zahlenteil mit optionalem Trenner wird entfernt:
  Trenner erlaubt: `.`, `_`, `-` oder **1–3 Leerzeichen**.
* **Dateien:** Erkennung/Ersetzung nur auf dem **Stammnamen**; die Extension bleibt unverändert.
* **Leerzeichen & Unicode:** Mehrfach-Spaces werden zu einem Space zusammengezogen; der Name wird in **NFC** normalisiert.
* **Beispiele:**

  * Ordner `001--- Fotos` → `000 Fotos` (bei `--start 0 --step 10 --width 3`)
  * Datei `12- Sommer.png` → `000 Sommer.png`

---

## Sortierreihenfolge (Originalordnung)

Innerhalb eines Verzeichnisses wird nach dem **Originalnamen** sortiert (nicht nach dem „Restnamen“), **case-insensitiv und locale-basiert**. Die Sortierung ist stabil.

---

## Rekursives Verhalten (nur `folders`)

* **Preorder** über den gesamten Baum (Eltern vor Kindern in der Sequenz).
* Es existiert **eine durchgehende Nummernfolge** über alle gefundenen Ordner.
* **Junctions/Symlinks** werden nicht verfolgt (Schleifenvermeidung).

---

## Sichtbarkeitsregeln & Filter

* **Versteckte/System-Einträge** (Windows-Attribute *Hidden*/*System*) werden **immer ignoriert**.
* **Symbolische Links/Junctions** werden **nicht** verarbeitet.
* **Lock-Verzeichnis** `.renum.lock` wird **immer ignoriert** und zusätzlich als **Hidden** markiert.

---

## Konfliktprüfung & Windows-Validierung

Vor jeder Ausführung wird geprüft:

1. **Doppelte Zielnamen** (case-insensitiv) innerhalb desselben Verzeichnisses.
2. **Kollisionen** mit unbeteiligten vorhandenen Einträgen (die nicht Teil der geplanten Umbenennungen sind).
3. **Windows-Name-Regeln:**

   * Verbotene Zeichen: `< > : " / \ | ? *`
   * Keine Namen, die auf **Punkt** oder **Leerzeichen** enden.
   * **Reservierte Basenamen** (ohne Extension) sind verboten: `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`.

Bei Konflikten bricht renum.py **ohne Änderungen** ab.

---

## Transaktionales Umbenennen (All-or-Nothing)

1. **Planen:** Vollständige Quell→Ziel-Liste wird berechnet.
2. **Phase A (Staging):** Alle betroffenen Einträge werden auf **eindeutige temporäre** Namen verschoben (`.renum_tmp_<uuid>`).

   * **Ordner rekursiv:** Staging **von Blatt zu Wurzel** (leaf→root), damit Kindpfade frei werden.
3. **Phase B (Commit):** Temporäre Namen werden in einem zweiten Schritt auf die **finalen Namen** umbenannt.

   * **Ordner rekursiv:** Commit **von Wurzel zu Blatt** (root→leaf).
4. **Rollback:** Tritt in Phase A oder B ein Fehler auf, wird **vollständig zurückgerollt**:

   * Bereits final umbenannte Einträge → zurück auf tmp,
   * tmp-Einträge → zurück auf den ursprünglichen Namen.

---

## Locking gegen Parallelläufe

* Beim Start legt renum.py unter `PATH` ein **Lock-Verzeichnis** `.\.renum.lock` an (inkl. `pid.txt`).
* Existiert es bereits, wird der Lauf mit Fehler beendet (kein paralleler Zugriff auf denselben Pfad).
* Das Lock wird beim Beenden wieder gelöscht. Bleibt es nach einem Abbruch liegen, kann man es **manuell entfernen** (sofern keine andere Instanz läuft).

---

## Ausgabe & Logging

* **DRY-RUN / PLAN**: Eine Zeile pro Änderung, z. B.
  `DRY-RUN: .\ALT -> .\NEU`
  (Bei echtem Lauf erscheint vorher `PLAN:` in gleichem Format.)
* **Zusammenfassung** am Ende: `Zusammenfassung: geprüft X, geplant Y`
* **Verbose-Modus (`--verbose`)**: Staging/Commit/Rollback-Schritte auf **stderr**.
* Alle Pfade relativ zum Root und im **Windows-Format** (`.\…`).

---

## Exit-Codes

* `0` – Erfolg (auch reiner Dry-Run ohne Konflikte)
* `1` – Fehler (Konflikte, IO/Permissions, Rollback nötig, Lock bereits vorhanden etc.)
* `2` – Falsche Plattform oder CLI-Nutzung/Abbruch mit Hilfe

---

## Beispiele

### 1) Ordner – nicht rekursiv, planen

```powershell
python renum.py folders "D:\Fotos\2024" --dry-run
```

Ausgabe (Beispiel):

```
DRY-RUN: .\001 Urlaub -> .\000 Urlaub
DRY-RUN: .\020 Arbeit -> .\010 Arbeit
Zusammenfassung: geprüft 2, geplant 2
```

### 2) Ordner – rekursiv, ausführen

```powershell
python renum.py folders "D:\Projekte" --recursive --go --start 0 --step 10 --width 3
```

* Durchgehende Sequenz über alle Unterordner.
* Änderungen werden transaktional durchgeführt.

### 3) Dateien – nur bestimmte Endungen, planen

```powershell
python renum.py files "C:\Bilder" --ext ".jpg,.png" --dry-run
```

* Berücksichtigt nur Dateien mit den angegebenen Endungen (case-insensitiv).
* Nie rekursiv.

---

## Vorher/Nachher – Beispiel

**Eingang (Dateien):**

```
.\10- Sonnenuntergang.jpg
.\ 2__ Abendhimmel .png
.\Urlaub.txt      (soll ignoriert werden, wenn --ext ".jpg,.png")
```

**Aufruf:**

```powershell
python renum.py files . --ext ".jpg,.png" --start 0 --step 10 --width 3 --go
```

**Ergebnis:**

```
.\000 Sonnenuntergang.jpg
.\010 Abendhimmel.png
.\Urlaub.txt                   (unverändert)
```

---

## Grenzen & Hinweise

* **Nicht rekursiv für Dateien.**
* **Keine** Option, versteckte/System-Einträge einzubeziehen.
* **Keine** Muster-Filter (kein `--pattern`).
* **Root-Pfad** darf **kein** Link/Junction sein (wird abgewiesen).
* **Sehr lange Pfade** können (je nach Windows-Konfiguration) zu IO-Fehlern führen.
* **Fehler während des Laufs** führen zu einem vollständigen **Rollback**.

---

## Troubleshooting (kurz)

* **„Sperre aktiv“** – Es existiert bereits `.\.renum.lock`:
  → Sicherstellen, dass keine Instanz läuft; ggf. Lock-Ordner manuell löschen.
* **„Zielname existiert bereits“ / „Ungültiger Windows-Name“** –
  → Parameter (Start/Step/Width) oder Ausgangsnamen prüfen; ggf. `--dry-run` ausführen, um Kollisionen zu sehen.
* **„Root-Pfad darf kein Link/Junction sein.“** –
  → Direkt auf das echte Zielverzeichnis zeigen.

---

## Best Practices

1. **Immer zuerst `--dry-run`** – Kollisionen früh sichtbar machen.
2. **Mit `--step 10` starten** – Lässt später Platz für Zwischeneinfügungen.
3. **Sinnvolle `--width`** wählen – z. B. 3 für bis zu 999 Einträge.
4. **Große Bäume**: Bei `folders --recursive` zunächst testen, dann erst `--go`.
