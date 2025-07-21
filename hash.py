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
from pathlib import Path
from lib.utils import find_audio_files, get_timestamp
import sys
from collections import defaultdict

VERSION = "1.0"


def scan(directory: Path, depth: int | None):
    """
    Finds all audio files under DIRECTORY and creates a hash list (one line per file).
    The output is written to a timestamped file.
    Prints hash and path for each file (with empty line).
    """
    timestamp = get_timestamp()
    outfilename = f"hash-scan-{timestamp}.txt"
    processed = 0
    error = None

    print(f"Starting scan in: {directory.resolve()}")
    print(f"Search depth: {'unlimited' if depth is None else depth}")
    print(f"Output file: {outfilename}\n")

    try:
        with open(outfilename, 'w', encoding='utf-8') as out:
            for relpath in find_audio_files(directory, absolute=False, depth=depth):
                try:
                    from lib.soundfile import sha256
                    hashval = sha256(directory / relpath)
                except Exception as e:
                    error = (relpath, e)
                    break
                # Write to output file
                out.write(f"{hashval} {relpath.as_posix()}\n")
                processed += 1
                # Print to console (hash, path, empty line)
                print(hashval)
                print(relpath.as_posix())
                print()
    except Exception as e:
        print(
            f"\n[ABORTED] Error writing to '{outfilename}': {e}", file=sys.stderr)
        print(f"Processed files before error: {processed}", file=sys.stderr)
        sys.exit(1)

    if error:
        relpath, exc = error
        print(f"\n[ABORTED] Error with file {relpath}: {exc}", file=sys.stderr)
        print(f"Processed files before error: {processed}", file=sys.stderr)
        sys.exit(1)
    else:
        print(
            f"\nAll {processed} files processed successfully – no error occurred!")
        print(f"Hash list written to: {outfilename}")


def parse_hash_file(path: Path):
    """
    Reads a hash file (format: <hash> <path>) and returns a dict:
    {hash: [list of paths]}
    """
    hashes = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue  # skip malformed line
            hashval, filepath = parts
            hashes[hashval].append(filepath)
    return hashes


def intersect(
    file1: Path,
    file2: Path,
    paths_from: str = "file1",
    save_dupes: bool = False
):
    """
    Finds common hashes between two files and writes result
    in format '<hash> <path>' (path taken from selected file).
    Optionally saves duplicate groups from the selected file.
    """
    timestamp = get_timestamp()
    outfile = f"hash-intersect-{timestamp}.txt"
    dupes_file = f"hash-intersect-dupes-{timestamp}.txt" if save_dupes else None

    # Read both files
    hashes1 = parse_hash_file(file1)
    hashes2 = parse_hash_file(file2)

    # Intersection: hashes that exist in both files
    common_hashes = set(hashes1) & set(hashes2)

    # For statistics
    total1 = sum(len(paths) for paths in hashes1.values())
    total2 = sum(len(paths) for paths in hashes2.values())
    total_common = len(common_hashes)

    # For --paths-from
    from_hashes = hashes1 if paths_from == "file1" else hashes2

    # Save main intersect file
    n_written = 0
    with open(outfile, "w", encoding="utf-8") as out:
        for h in sorted(common_hashes):
            for path in from_hashes[h]:
                out.write(f"{h} {path}\n")
                n_written += 1

    # Save dupes if requested
    n_dupe_groups = 0
    n_dupe_files = 0
    if save_dupes:
        with open(dupes_file, "w", encoding="utf-8") as dfile:
            for h in sorted(common_hashes):
                paths = from_hashes[h]
                if len(paths) > 1:
                    n_dupe_groups += 1
                    n_dupe_files += len(paths)
                    dfile.write(f"{h}\n")
                    for path in paths:
                        dfile.write(f"{path}\n")
                    dfile.write("\n")

    # Output stats
    print()
    print("---- INTERSECT SUMMARY ----")
    print(f"Hashes in {file1}: {len(hashes1)} (total paths: {total1})")
    print(f"Hashes in {file2}: {len(hashes2)} (total paths: {total2})")
    print(f"Common hashes: {total_common}")
    print(f"Lines written: {n_written} (to {outfile})")
    if save_dupes:
        print(f"Duplicate hash groups (in {paths_from}): {n_dupe_groups}")
        print(f"Total dupe files: {n_dupe_files}")
        if n_dupe_groups > 0:
            print(f"Dupe groups saved to: {dupes_file}")
        else:
            print("No duplicate hashes found in selected file.")
    print("---------------------------\n")
    print("No errors occurred.")


def diff(
    file1: Path,
    file2: Path,
    from_side: str | None = None,   # 'file1', 'file2', or None (both)
    save_dupes: bool = False
):
    """
    Finds all lines in file1 that are not in file2 (and/or vice versa), based on hash.
    Optionally saves duplicate groups.
    """
    timestamp = get_timestamp()
    hashes1 = parse_hash_file(file1)
    hashes2 = parse_hash_file(file2)

    set1 = set(hashes1)
    set2 = set(hashes2)

    only1 = set1 - set2
    only2 = set2 - set1

    total1 = sum(len(paths) for paths in hashes1.values())
    total2 = sum(len(paths) for paths in hashes2.values())

    outfiles = []
    dupefiles = []
    stats = []

    # Helper for writing diff output & dupes for one direction
    def write_diff_and_dupes(only, hashes_from, name):
        outfilename = f"hash-diff-{name}-{timestamp}.txt"
        outfiles.append(outfilename)
        n_diff_lines = 0

        with open(outfilename, "w", encoding="utf-8") as out:
            for h in sorted(only):
                for path in hashes_from[h]:
                    out.write(f"{h} {path}\n")
                    n_diff_lines += 1

        n_dupe_groups = 0
        n_dupe_files = 0
        dupefilename = None

        if save_dupes:
            # Write dupes file in block format
            dupefilename = f"hash-diff-{name}-dupes-{timestamp}.txt"
            dupefiles.append(dupefilename)
            with open(dupefilename, "w", encoding="utf-8") as df:
                for h in sorted(only):
                    paths = hashes_from[h]
                    if len(paths) > 1:
                        n_dupe_groups += 1
                        n_dupe_files += len(paths)
                        df.write(f"{h}\n")
                        for path in paths:
                            df.write(f"{path}\n")
                        df.write("\n")
        return n_diff_lines, n_dupe_groups, n_dupe_files, outfilename, dupefilename

    print()
    print("---- DIFF SUMMARY ----")
    print(f"Hashes in {file1}: {len(hashes1)} (total paths: {total1})")
    print(f"Hashes in {file2}: {len(hashes2)} (total paths: {total2})")

    # No --from → both directions, else only selected direction
    if from_side is None or from_side == "file1":
        n_diff1, n_dupe1, n_dupef1, of1, df1 = write_diff_and_dupes(
            only1, hashes1, "file1")
        stats.append((f"file1", n_diff1, n_dupe1, n_dupef1, of1, df1))
    if from_side is None or from_side == "file2":
        n_diff2, n_dupe2, n_dupef2, of2, df2 = write_diff_and_dupes(
            only2, hashes2, "file2")
        stats.append((f"file2", n_diff2, n_dupe2, n_dupef2, of2, df2))

    for side, n_diff, n_dupe, n_dupef, ofile, dfile in stats:
        print(f"Unique hashes in {side}: {n_diff}")
        print(f"Diff lines written to: {ofile}")
        if save_dupes:
            print(
                f"Duplicate hash groups in {side}: {n_dupe} (total paths: {n_dupef})")
            if n_dupe > 0:
                print(f"Dupe groups saved to: {dfile}")
            else:
                print("No duplicate hashes found in this diff.")
        print()

    print("----------------------")
    print("No errors occurred.")


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for generating SHA256 hash lists for audio files (recursive)."
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="command"
    )

    # Scan subcommand
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan directory for audio files and generate hash list"
    )
    scan_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        type=Path,
        help="Root directory to scan (default: current directory)"
    )
    scan_parser.add_argument(
        "--depth", "-d",
        type=int,
        default=None,
        help="Maximum search depth (0 = only the root directory, default: unlimited)"
    )

    # Intersect subcommand
    intersect_parser = subparsers.add_parser(
        "intersect",
        help="Find common hashes between two hash files"
    )
    intersect_parser.add_argument(
        "file1", type=Path, help="First hash file (format: <hash> <path>)"
    )
    intersect_parser.add_argument(
        "file2", type=Path, help="Second hash file (format: <hash> <path>)"
    )
    intersect_parser.add_argument(
        "--paths-from",
        choices=["file1", "file2"],
        default="file1",
        help=(
            "Which file to take paths from for the output (default: file1). "
            "If you use --save-dupes, duplicate groups will be saved with paths from the same file."
        )
    )
    intersect_parser.add_argument(
        "--save-dupes",
        action="store_true",
        help="Additionally save all duplicate hashes (with paths) from the selected file in a separate file"
    )

    diff_parser = subparsers.add_parser(
        "diff",
        help="Find lines that are unique to one hash file compared to another"
    )
    diff_parser.add_argument(
        "file1", type=Path, help="First hash file (format: <hash> <path>)"
    )
    diff_parser.add_argument(
        "file2", type=Path, help="Second hash file (format: <hash> <path>)"
    )
    diff_parser.add_argument(
        "--from",
        dest="from_side",
        choices=["file1", "file2"],
        default=None,
        help="Show only lines unique to the specified file (default: both directions)"
    )
    diff_parser.add_argument(
        "--save-dupes",
        action="store_true",
        help="Additionally save all duplicate hashes (with paths) from the diffed file(s) in a separate file"
    )

    args = parser.parse_args()

    # Show help if no subcommand was given
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # If command is 'scan', run the scan function
    if args.command == "scan":
        if not args.directory.exists() or not args.directory.is_dir():
            print(
                f"Error: Directory '{args.directory}' does not exist or is not a directory.", file=sys.stderr)
            sys.exit(1)
        scan(args.directory, args.depth)

    elif args.command == "intersect":
        for f in (args.file1, args.file2):
            if not f.exists():
                print(
                    f"Error: Hash file '{f}' does not exist.", file=sys.stderr)
                sys.exit(1)
        intersect(
            args.file1,
            args.file2,
            paths_from=args.paths_from,
            save_dupes=args.save_dupes
        )

    elif args.command == "diff":
        for f in (args.file1, args.file2):
            if not f.exists():
                print(
                    f"Error: Hash file '{f}' does not exist.", file=sys.stderr)
                sys.exit(1)
        diff(
            args.file1,
            args.file2,
            from_side=args.from_side,
            save_dupes=args.save_dupes
        )


if __name__ == "__main__":
    main()
