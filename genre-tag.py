import argparse
from pathlib import Path
from lib.utils import find_audio_files
from lib.tagging import set_tags
import sys
import re


def clean_folder_name(name: str) -> str:
    """
    Entfernt führende Zahlen + Leerzeichen aus einem Ordnernamen.
    Beispiel: "01 House" -> "House"
    """
    return re.sub(r"^\d+\s+", "", name).title()


def build_genre_tag(file_path: Path, root_path: Path, include_root: bool) -> str:
    rel_parts = file_path.parent.relative_to(root_path).parts
    if include_root:
        genre_parts = [root_path.name] + list(rel_parts)
    else:
        genre_parts = list(rel_parts)
    return " / ".join(clean_folder_name(part) for part in genre_parts if part)


def main():
    parser = argparse.ArgumentParser(
        description="Setzt Genre-Tags basierend auf der Ordnerstruktur")
    parser.add_argument("--dry-run", action="store_true",
                        help="Keine Dateien schreiben, nur anzeigen")
    parser.add_argument("--no-root", action="store_true",
                        help="Aktuellen Ordnernamen ausschließen und Dateien im Root ignorieren")
    args = parser.parse_args()

    root = Path(".").resolve()
    flac_files = list(find_audio_files(root, absolute=True))

    if args.no_root:
        flac_files = [f for f in flac_files if f.parent != root]

    if not flac_files:
        print("[INFO] Keine geeigneten FLAC-Dateien gefunden.")
        return

    failed = []

    for file_path in flac_files:
        try:
            genre = build_genre_tag(file_path, root, not args.no_root)
            print(f"{file_path.relative_to(root)} → genre = {genre}")
            if not args.dry_run:
                set_tags(file_path, {"genre": genre}, overwrite=True)
        except Exception as e:
            print(f"[FEHLER] {file_path}: {e}", file=sys.stderr)
            failed.append(file_path)

    if failed:
        print("\n[ABBRUCH] Fehlerhafte Dateien:")
        for f in failed:
            print(f" - {f.relative_to(root)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
