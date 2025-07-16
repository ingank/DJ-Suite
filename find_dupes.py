"""
find_dupes.py

Vergleicht zwei Hashdateien im Format:
    <sha256> <relativer/pfad/zur/datei>

und gibt alle Zeilen aus der ersten Datei aus, deren Hash
auch in der zweiten Datei vorhanden ist ("Dubletten" bezogen auf Datei 2).

Optional mit --clean: Nur das erste Vorkommen jedes Duplikat-Hashes ausgeben.

Benutzung:
    python find_dupes.py hashdatei1.txt hashdatei2.txt [--clean]

Beispiel:
    python find_dupes.py archiv_hashes.txt stage_hashes.txt --clean

Das Skript hilft beim Finden von Audiodateien, die sowohl in Datei 1
(z.B. Archiv) als auch in Datei 2 (z.B. Arbeitskopien, neue Downloads)
enthalten sind – auch wenn die Pfade unterschiedlich sind.
"""

import sys

if not (3 <= len(sys.argv) <= 4):
    print("\nVergleicht zwei Hashdateien im Format:\n"
          "    <sha256> <relativer/pfad/zur/datei>\n"
          "\n"
          "Gibt alle Zeilen aus der ersten Datei aus, deren Hash auch in Datei 2 enthalten ist.\n"
          "\n"
          "Mit Option --clean wird pro Hash nur das erste Vorkommen ausgegeben.\n"
          "\n"
          "Nutzung:\n"
          "    python find_dupes.py hashdatei1.txt hashdatei2.txt [--clean]\n"
          "\n"
          "Beispiel:\n"
          "    python find_dupes.py archiv_hashes.txt stage_hashes.txt --clean\n"
          "\n"
          "Das ist hilfreich, um Duplikate zwischen verschiedenen Musikarchiven zu erkennen.\n")
    sys.exit(1)

file1, file2 = sys.argv[1], sys.argv[2]
CLEAN = len(sys.argv) == 4 and sys.argv[3] == "--clean"


def load_hashes(filename):
    """Liest alle SHA256-Hashes aus einer Hashdatei ins Set ein (nur 64 Zeichen am Zeilenanfang)."""
    hashes = set()
    with open(filename, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sha = line.split(maxsplit=1)[0]
            if sha and len(sha) == 64:
                hashes.add(sha)
    return hashes


hashes2 = load_hashes(file2)

seen = set()

with open("DUPES.txt", "w", encoding="utf-8") as outfile:
    with open(file1, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sha = line.split(maxsplit=1)[0]
            if sha and len(sha) == 64 and sha in hashes2:
                if CLEAN:
                    if sha in seen:
                        continue
                    seen.add(sha)
                print(line)
                outfile.write(line + "\n")
