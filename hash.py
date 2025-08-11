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

import shutil
import argparse
from pathlib import Path
from lib.hash import scan, match, write, read, dupes, diff
from lib.hash import sort_by_path, sort_by_hash_path, sha256_iter
from lib.file import get_tags
from lib.utils import make_filename, find_audio_files
from lib.config import STAGE_ROOT


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

    # SORT
    sort_parser = subparsers.add_parser(
        "sort", help="Sortiert eine Hashdatei nach Pfad")
    sort_parser.add_argument(
        "hashfile", help="Hashdatei, die sortiert werden soll")

    # MERGE
    merge_parser = subparsers.add_parser(
        "merge", help="Vereint zwei Hashdateien zu einer neuen Datei (ohne Dubletten)."
    )
    merge_parser.add_argument("hashfile1", help="Erste Hashdatei")
    merge_parser.add_argument("hashfile2", help="Zweite Hashdatei")

    # COPY
    copy_parser = subparsers.add_parser(
        "copy", help="Kopiert alle Dateien aus einer Hashdatei in einen neuen Ordner (mit Struktur)")
    copy_parser.add_argument(
        "hashfile", help="Hashdatei, aus der kopiert wird")

    # MOVE
    move_parser = subparsers.add_parser(
        "move",
        help="Verschiebt alle in einer Hashdatei gelisteten Dateien in einen neuen Ordner (mit Struktur)"
    )
    move_parser.add_argument(
        "hashfile",
        help="Hashdatei, deren Dateien verschoben werden sollen"
    )

    # READ
    read_parser = subparsers.add_parser(
        "read",
        help="Liest SHA256-Tags (gen0-sha256) aus Audiodateien und schreibt eine Hash-Datei"
    )

    args = parser.parse_args()

    if args.command == "scan":
        root = Path(args.directory).resolve()
        rel_files = find_audio_files(root, absolute=False)  # RELATIVE Pfade
        outfile = make_filename("hash-scan")
        for line in write(outfile, sha256_iter(root, rel_files)):
            print(line)

    elif args.command == "diff":
        """
        Gibt alle (hash, path) aus source1 zurück, deren Hash NICHT in source2 vorkommt.
        Reihenfolge bleibt wie in source1. In-File-Dubletten werden geliefert.
        """
        diffs = list(diff(read(args.hashfile1), read(args.hashfile2)))
        outfile = make_filename("hash-diff")
        for line in write(outfile, iter(diffs)):
            print(line)

    elif args.command == "match":
        """
        Gibt alle (hash, path) aus source1 zurück, deren hash auch in source2 vorkommt.
        Reihenfolge bleibt wie in source1. In-File-Dubletten werden geliefert.
        """
        matches = list(match(read(args.hashfile1), read(args.hashfile2)))
        outfile = make_filename("hash-match")
        for line in write(outfile, iter(matches)):
            print(line)

    elif args.command == "dupes":
        all_lines = list(read(args.hashfile))
        dupes_dict = dupes(all_lines)

        if args.raw:
            # Reihenfolge wie im Originalfile (raw)
            dupes_lines = [(hashval, path)
                           for hashval, path
                           in all_lines
                           if hashval in dupes_dict]
        else:
            # Alphabetisch nach Hash und dann Pfad
            dupes_lines = sort_by_hash_path(
                [(hashval, path)
                 for hashval, path
                 in all_lines
                 if hashval in dupes_dict]
            )

        outfile = make_filename("hash-dupes")
        for line in write(outfile, dupes_lines):
            print(line)

    elif args.command == "sort":
        lines = list(read(args.hashfile))
        sorted_lines = sort_by_path(lines)
        outfile = make_filename("hash-sorted")
        for line in write(outfile, sorted_lines):
            print(line)

    elif args.command == "merge":
        lines1 = list(read(args.hashfile1))
        lines2 = list(read(args.hashfile2))
        merged_set = set(lines1) | set(lines2)
        merged_list = sort_by_path(merged_set)
        outfile = make_filename("hash-merge")
        for line in write(outfile, merged_list):
            print(line)

    elif args.command == "copy":
        # Timestamp/Name für Ordner und Datei (synchron)
        basename = make_filename("copy", ext="").stem
        outdir = Path(STAGE_ROOT) / basename
        outfile = outdir / f"{basename}.txt"

        # Hashfile lesen & Existenz prüfen
        all_lines = list(read(args.hashfile))
        missing = [p for _, p in all_lines if not Path(p).is_file()]
        if missing:
            print("FEHLER: Nicht alle Dateien aus der Hashdatei existieren. Abbruch.")
            exit(1)

        # Zielordner anlegen
        outdir.mkdir(parents=True, exist_ok=True)

        # Kopier-Generator
        def copy_and_yield(lines):
            for hashval, relpath in lines:
                src = Path(relpath)
                dst = outdir / relpath
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                yield hashval, relpath

        # Ausgeben & Schreiben
        for line in write(outfile, copy_and_yield(all_lines)):
            print(line)

    elif args.command == "move":
        # Timestamp/Name für Ordner und Datei (synchron)
        basename = make_filename("move", ext="").stem
        outdir = Path(STAGE_ROOT) / basename
        outfile = outdir / f"{basename}.txt"

        # Hashfile lesen & Existenz prüfen
        all_lines = list(read(args.hashfile))
        missing = [p for _, p in all_lines if not Path(p).is_file()]
        if missing:
            print("FEHLER: Nicht alle Dateien aus der Hashdatei existieren. Abbruch.")
            exit(1)

        # Zielordner anlegen
        outdir.mkdir(parents=True, exist_ok=True)

        # Verschiebe-Generator
        def move_and_yield(lines):
            for hashval, relpath in lines:
                src = Path(relpath)
                dst = outdir / relpath
                dst.parent.mkdir(parents=True, exist_ok=True)
                # shutil.move akzeptiert nur Strings!
                shutil.move(str(src), str(dst))
                yield hashval, relpath

        # Ausgeben & Schreiben
        for line in write(outfile, move_and_yield(all_lines)):
            print(line)

    elif args.command == "read":
        files = find_audio_files(".", absolute=False, filter_ext=[".flac"])
        if not files:
            print("[INFO] Keine Audiodateien gefunden.")
            exit(0)

        missing = []
        results = []

        for relpath in files:
            file = Path('.') / relpath
            hashval = get_tags(file, "gen0-sha256")
            print(".", end="", flush=True)  # Fortschrittspunkt pro Datei
            if not hashval:
                missing.append(relpath)
            else:
                results.append((hashval, relpath.as_posix()))

        print()

        if missing:
            print(
                "[ERROR] Die folgenden Dateien haben keinen gültigen GEN0-SHA256-Tag:")
            for relpath in missing:
                print(f"  - {relpath}")
            print("\n[ABBRUCH] Vorgang wurde beendet. Keine Hash-Datei geschrieben.")
            exit(1)

        outfile = make_filename("hash-read")
        for line in write(outfile, iter(results)):
            print(line)


if __name__ == "__main__":
    main()
