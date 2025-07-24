# hash.py (main)

import argparse
from datetime import datetime
from pathlib import Path
from lib.hash import scan, match, write, read, dupes, diff
from lib.utils import make_filename


def main():
    parser = argparse.ArgumentParser(description="Hash-Toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # SCAN
    scan_parser = subparsers.add_parser(
        "scan", help="Verzeichnis scannen und Hashes ausgeben")
    scan_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Verzeichnis zum Scannen (Standard: aktuelles Verzeichnis)"
    )

    # DIFF
    diff_parser = subparsers.add_parser(
        "diff", help="Vergleicht zwei Hashdateien und zeigt Unterschiede")
    diff_parser.add_argument("hashfile1", help="Erste Hashdatei")
    diff_parser.add_argument("hashfile2", help="Zweite Hashdatei")

    # MATCH
    match_parser = subparsers.add_parser(
        "match", help="Zeigt Pfade aus Datei 1, die auch in Datei 2 vorhanden sind")
    match_parser.add_argument("hashfile1", help="Erste Hashdatei")
    match_parser.add_argument("hashfile2", help="Zweite Hashdatei")

    args = parser.parse_args()

    if args.command == "scan":
        # Generator für Scan-Ergebnisse (hash, path)
        results = scan(args.directory)
        outfile = make_filename("hash-scan")
        for line in write(outfile, results):
            print(line)

    elif args.command == "diff":

        # Generator erzeugen und als Liste materialisieren (für Mehrfachnutzung):
        diffs = list(diff(read(args.hashfile1), read(args.hashfile2)))
        outfile = make_filename("hash-diff")
        for line in write(outfile, iter(diffs)):
            print(line)

        # Duplikate unter den „left-only“-Ergebnissen anzeigen
        dupes_dict = dupes(diffs)
        if dupes_dict:
            print("\nDuplikate aus Datei 1 (Hash mehrmals):\n")
            for hashval in sorted(dupes_dict):
                print(hashval)
                for p in sorted(dupes_dict[hashval]):
                    print(p)
                print()
        else:
            print("\nKeine Duplikate aus Datei 1 gefunden.")

    elif args.command == "match":
        # 1. Alle Treffer aus Datei 1, deren Hash auch in Datei 2 vorkommt (Originalreihenfolge)
        matches = list(match(read(args.hashfile1), read(args.hashfile2)))

        # 2. Schreibe die Hash-Matches ins File und gib gleichzeitig alles aus
        outfile = make_filename("hash-match")
        for line in write(outfile, iter(matches)):
            print(line)

        # 3. Duplikate aus matches anzeigen (Hash mehrfach in Datei 1)
        dupes_dict = dupes(matches)
        if dupes_dict:
            print("\nDuplikate aus Datei 1 (Hash mehrmals):\n")
            for hashval in sorted(dupes_dict):
                print(hashval)
                for p in sorted(dupes_dict[hashval]):
                    print(p)
                print()
        else:
            print("\nKeine Duplikate aus Datei 1 gefunden.")


if __name__ == "__main__":
    main()
