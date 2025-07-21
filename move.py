"""
move.py

Verschiebt alle in einer Hashdatei gelisteten Dateien (relativer Pfad)
in einen Unterordner MOVE-<zeitstempel>, behält dabei die Original-Unterordnerstruktur bei.

Vor dem Verschieben wird geprüft, ob ALLE gelisteten Dateien existieren.
Bei fehlenden Dateien bricht das Skript ab und listet bis zu drei Beispiele.

Benutzung:
    python move.py hashdatei.txt
"""

import sys
import os
import shutil
from pathlib import Path
from lib.utils import get_timestamp


def print_usage_and_exit():
    print("Fehler: Falsche Benutzung!\n")
    print("Benutzung:\n  python move.py hashdatei.txt\n")
    sys.exit(1)


def load_file_paths(hashdatei):
    """
    Liest alle relativen Dateipfade aus der Hashdatei.
    Gibt eine Liste von Pfaden zurück.
    """
    pfade = []
    try:
        with open(hashdatei, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2 and len(parts[0]) == 64:
                    pfade.append(parts[1])
    except Exception as e:
        print(f"Fehler beim Lesen von '{hashdatei}': {e}")
        sys.exit(1)
    return pfade


def check_all_exist(pfade):
    """
    Prüft, ob alle angegebenen relativen Pfade existieren (ausgehend vom aktuellen Ordner).
    Gibt ein Tupel zurück: (bool, fehlende_pfade_liste)
    """
    fehlende = []
    for pfad in pfade:
        if not Path(pfad).is_file():
            fehlende.append(pfad)
            if len(fehlende) >= 3:
                break  # Nur maximal drei Beispiele erfassen
    return (len(fehlende) == 0, fehlende)


def main():
    # --- Argumente prüfen ---
    if len(sys.argv) != 2:
        print_usage_and_exit()
    hashdatei = sys.argv[1]

    # --- Dateipfade laden ---
    pfade = load_file_paths(hashdatei)

    if not pfade:
        print("Keine gültigen Dateipfade in der Hashdatei gefunden. Vorgang abgebrochen.")
        sys.exit(1)

    # --- Existenz-Check ---
    alles_da, fehlende = check_all_exist(pfade)
    if not alles_da:
        print(
            "Fehler: Nicht alle Dateien existieren im aktuellen Ordner oder Unterordnern.")
        for pfad in fehlende:
            print(f"  Nicht gefunden: {pfad}")
        rest = len([p for p in pfade if not Path(p).is_file()]) - len(fehlende)
        if rest > 0:
            print(f"  ...und {rest} weitere nicht gefunden.")
        print("\nEs wurde NICHTS verschoben. Vorgang abgebrochen.")
        sys.exit(1)

    # --- Zielordner & Logfile vorbereiten ---
    ts = get_timestamp()
    zielordner = Path(f"MOVE-{ts}")
    logfile = Path(f"move-{ts}.log")

    try:
        zielordner.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Fehler beim Erstellen des Zielordners '{zielordner}': {e}")
        sys.exit(1)

    # --- Dateien verschieben ---
    erfolgreich = 0
    fehler = 0
    with open(logfile, "w", encoding="utf-8") as log:
        for pfad in pfade:
            quellpfad = Path(pfad)
            zielpfad = zielordner / quellpfad
            try:
                zielpfad.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(quellpfad), str(zielpfad))
                print(f"verschoben: {pfad} -> {zielpfad}")
                log.write(f"verschoben: {pfad} -> {zielpfad}\n")
                erfolgreich += 1
            except Exception as e:
                print(f"Fehler beim Verschieben: {pfad} ({e})")
                log.write(f"FEHLER: {pfad} ({e})\n")
                fehler += 1

    # --- Statistik ---
    print("\nGesamtpfade in Hashdatei:   ", len(pfade))
    print("Erfolgreich verschoben:      ", erfolgreich)
    print("Fehler beim Verschieben:     ", fehler)
    print(f"\nLogdatei: {logfile}")
    print("\nProgramm erfolgreich beendet, kein Fehler." if fehler ==
          0 else "\nProgramm beendet, Fehler siehe oben.")


if __name__ == "__main__":
    main()
