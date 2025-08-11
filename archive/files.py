# files.py (CLI)

import argparse
from pathlib import Path
from lib.utils import find_audio_files
from lib.file import renew_flac


def handle_renew(args):
    files = find_audio_files(args.dir, absolute=True, filter_ext=[".flac"])
    if not files:
        return

    old_files = []

    for file in files:
        print(f"[RENEW] {file}")
        # bricht bei Fehler sofort mit Exception ab
        new_file = renew_flac(Path(file))
        old_file = Path(file).with_suffix(".flac.old")

        Path(file).rename(old_file)
        new_file.rename(file)

        old_files.append(old_file)

    if args.delete_old:
        removed = 0
        for of in old_files:
            if of.exists():
                of.unlink()
                removed += 1
        print(f"[CLEANUP] removed {removed} .flac.old")


def main():
    parser = argparse.ArgumentParser(description="File-Werkzeuge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    renew_parser = subparsers.add_parser(
        "renew", help="FLAC-Dateien re-encodieren (mit Padding & COMMENT)")
    renew_parser.add_argument(
        "dir", nargs="?", default=".", help="Startverzeichnis (Standard: aktuelles)")
    renew_parser.add_argument(
        "--delete-old", action="store_true", help="Alle .flac.old am Ende löschen")

    args = parser.parse_args()

    if args.command == "renew":
        handle_renew(args)
    # elif args.command == "andere":
    #     handle_andere(args)


if __name__ == "__main__":
    main()
