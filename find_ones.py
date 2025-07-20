"""
find_ones.py

Vergleicht zwei Hashdateien im Format:
    <sha256> <relativer/pfad/zur/datei>

Gibt alle Zeilen aus Datei 1 aus, deren Hash NICHT in Datei 2 enthalten ist.
Alle Ausgaben landen auch in einer Datei mit Timestamp.
Am Ende erfolgt eine übersichtliche Statistik.
"""

import sys
from lib.utils import get_timestamp


def print_usage_and_exit():
    print("Fehler: Falsche Benutzung!\n")
    print("Benutzung:\n  python find_ones.py hashdatei1.txt hashdatei2.txt\n")
    sys.exit(1)


def load_hashes(filename):
    """Liest alle SHA256-Hashes aus einer Datei und gibt sie als Set zurück."""
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

    # --- Hashes aus Datei 2 einlesen ---
    hashes2 = load_hashes(file2)

    # --- Hashes aus Datei 1 zählen ---
    hashes1 = set()
    zeilen_ausgabe = []
    gesamt_zeilen = 0

    try:
        with open(file1, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue
                sha, pfad = parts
                if len(sha) == 64:
                    hashes1.add(sha)
                    gesamt_zeilen += 1
                    if sha not in hashes2:
                        zeilen_ausgabe.append(line)
    except Exception as e:
        print(f"Fehler beim Lesen von '{file1}': {e}")
        sys.exit(1)

    # --- Ausgabedatei ---
    outfile_name = f"find_ones-{get_timestamp()}.txt"
    try:
        with open(outfile_name, "w", encoding="utf-8") as outfile:
            for line in zeilen_ausgabe:
                outfile.write(line + "\n")
    except Exception as e:
        print(f"Fehler beim Schreiben der Ausgabedatei: {e}")
        sys.exit(1)

    # --- Bildschirm-Ausgabe ---
    for line in zeilen_ausgabe:
        print(line)

    # --- Statistik ---
    print("\nHashes in Datei 1:       ", len(hashes1))
    print("Hashes in Datei 2:       ", len(hashes2))
    print("Zeilen nur in Datei 1:   ", len(zeilen_ausgabe))
    print("\nProgramm erfolgreich beendet, kein Fehler.")


if __name__ == "__main__":
    main()
