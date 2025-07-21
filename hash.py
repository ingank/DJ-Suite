"""
hash.py

CLI tool for generating SHA256 hash lists for audio files (recursive).
Subcommand 'scan' with directory and depth options.
Standard library only (argparse).
"""

import argparse
from pathlib import Path
from lib.utils import find_audio_files, get_timestamp
import sys

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


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for generating SHA256 hash lists for audio files (recursive)."
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="command"
    )

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


if __name__ == "__main__":
    main()
