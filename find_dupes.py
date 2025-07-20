"""
find_dupes.py

Vergleicht zwei Hashdateien im Format:
    <sha256> <relativer/pfad/zur/datei>

Findet alle Duplikate zwischen Datei 1 und Datei 2 anhand der Hashes,
gibt das erste Vorkommen jedes Hashes und die Mehrfachduplikate aus.
Schreibt die Ergebnisse mit Timestamp in eine Datei.
"""

import sys
from collections import defaultdict
from lib.utils import get_timestamp


def print_usage_and_exit():
    print("Fehler: Falsche Benutzung!\n")
    print("Benutzung:\n  python find_dupes.py hashdatei1.txt hashdatei2.txt\n")
    sys.exit(1)


def load_hashes(filename):
    """
    Liest alle SHA256-Hashes aus einer Datei.
    Gibt ein Set zurück.
    """
    hashes = set()
    try:
        with open(filename, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sha = line.split(maxsplit=1)[0]
                if sha and len(sha) == 64:
                    hashes.add(sha)
    except Exception as e:
        print(f"Fehler beim Lesen von '{filename}': {e}")
        sys.exit(1)
    return hashes


def main():
    # --- Argumente prüfen ---
    if len(sys.argv) != 3:
        print_usage_and_exit()
    file1, file2 = sys.argv[1], sys.argv[2]

    # --- Hashes aus Datei 1 und Datei 2 einlesen ---
    hashes1 = load_hashes(file1)
    hashes2 = load_hashes(file2)

    # --- Duplikate sammeln: Hash -> Liste aller Pfade aus Datei 1 ---
    dupe_lines = defaultdict(list)
    try:
        with open(file1, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue  # Zeile ignorieren, falls sie kein Pfad ist
                sha, pfad = parts
                if len(sha) == 64 and sha in hashes2:
                    dupe_lines[sha].append(pfad)
    except Exception as e:
        print(f"Fehler beim Lesen von '{file1}': {e}")
        sys.exit(1)

    # --- Ausgabe-Datei schreiben ---
    outfile_name = f"find_dupes-{get_timestamp()}.txt"
    try:
        with open(outfile_name, "w", encoding="utf-8") as outfile:
            for sha, pfade in dupe_lines.items():
                # Nur das erste Vorkommen schreiben
                outfile.write(f"{sha} {pfade[0]}\n")
    except Exception as e:
        print(f"Fehler beim Schreiben der Ausgabedatei: {e}")
        sys.exit(1)

    # --- Bildschirm-Ausgabe: Hash und erstes Vorkommen ---
    for sha, pfade in dupe_lines.items():
        print(sha)
        print(pfade[0])

    # --- Mehrfachduplikate ausgeben ---
    multi_dupes = {sha: pfade for sha,
                   pfade in dupe_lines.items() if len(pfade) > 1}
    if multi_dupes:
        print("\nMehrfachduplikate (gleicher Hash, mehrere Pfade in Datei 1):")
        for sha, pfade in multi_dupes.items():
            print(f"{sha} ({len(pfade)} Vorkommen):")
            for pfad in pfade:
                print(pfad)

    # --- Statistik ---
    print("\nHashes in Datei 1:       ", len(hashes1))
    print("Hashes in Datei 2:       ", len(hashes2))
    print("Duplikate gefunden:      ", len(dupe_lines))
    print("Mehrfachduplikate:       ", len(multi_dupes))
    print("\nProgramm erfolgreich beendet, kein Fehler.")


if __name__ == "__main__":
    main()
