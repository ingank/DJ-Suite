"""
find_ones.py

Vergleicht zwei Hashdateien im Format:
    <sha256> <relativer/pfad/zur/datei>

und gibt alle Zeilen aus Datei 1 aus, deren Hash NICHT in Datei 2 enthalten ist.
Alle Bildschirmausgaben landen zusätzlich in ONES.txt.

Benutzung:
    python find_ones.py hashdatei1.txt hashdatei2.txt
"""

import sys

if len(sys.argv) != 3:
    print("Aufruf: python find_ones.py hashdatei1.txt hashdatei2.txt")
    sys.exit(1)

file1, file2 = sys.argv[1], sys.argv[2]


def load_hashes(filename):
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

with open("ONES.txt", "w", encoding="utf-8") as outfile:
    with open(file1, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sha = line.split(maxsplit=1)[0]
            if sha and len(sha) == 64 and sha not in hashes2:
                print(line)
                outfile.write(line + "\n")
