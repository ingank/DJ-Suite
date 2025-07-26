"""
hash.py

Multifunctional CLI tool for managing audio file hashes.

Subcommands:
  - scan:      Recursively hash all audio files in a directory and output a hash list.
  - intersect: Find common hashes (intersection) between two hash files, 
               with flexible source selection for paths and optional duplicate reporting.
  - diff:      Find all lines from one hash file that are not present in another,
               with support for both directions, per-direction output, and optional duplicate reporting.

Features:
  - Simple, line-based hash file format: <hash> <relative/path/to/file>
  - Flexible output and filtering for intersections and differences
  - Handles duplicate hashes (multiple files with same content)
  - Optional statistics and detailed reports
  - Pure Python, only standard library (argparse, pathlib, etc.)
  - Robust error handling and clear console output

Usage examples:
  python hash.py scan [DIRECTORY] [--depth N]
  python hash.py intersect file1.txt file2.txt [--paths-from {file1,file2}] [--save-dupes]
  python hash.py diff file1.txt file2.txt [--from {file1,file2}] [--save-dupes]

Hash file format:
  Each line: <sha256-hash> <relative/path/to/file>
  Example:   1a2b3c4d...  music/album/track.mp3

(c) 2024-2025, Your Name or Organization
"""

import argparse
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

    # DUPES
    dupes_parser = subparsers.add_parser(
        "dupes", help="Listet alle Hash-Dubletten aus einer Hashdatei")
    dupes_parser.add_argument("hashfile", help="Hashdatei zur Duplikatsuche")
    dupes_parser.add_argument(
        "--raw",
        action="store_true",
        help="Dubletten in Originalreihenfolge (nicht sortiert) ausgeben"
    )

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

    elif args.command == "dupes":
        all_lines = list(read(args.hashfile))
        dupes_dict = dupes(all_lines)

        # Zeilen für Ausgabe generieren (immer alle Dubletten-Zeilen, aber Reihenfolge je nach Option)
        if args.raw:
            # Reihenfolge wie im Originalfile (raw)
            dupes_lines = ((hashval, path)
                           for hashval, path in all_lines if hashval in dupes_dict)
        else:
            # Alphabetisch nach Hash und dann Pfad
            dupes_lines = sorted(
                ((hashval, path) for hashval, paths in dupes_dict.items()
                 for path in paths),
                key=lambda t: (t[0], t[1])
            )

        outfile = make_filename("hash-dupes")
        for line in write(outfile, dupes_lines):
            print(line)


if __name__ == "__main__":
    main()
