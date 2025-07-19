"""
count.py

Zählt alle gängigen Audiodateien im aktuellen Ordner und in allen Unterordnern
und gibt zusätzliche Statistik aus (auch Dubletten).
"""

from pathlib import Path
from collections import Counter, defaultdict
from lib.utils import find_audio_files

# Erweiterte Liste ALLER üblichen Audioformate (wird immer benutzt)
EXTENDED_EXTENSIONS = [
    '.wav', '.aiff', '.aifc', '.mp3', '.flac',
    '.aac', '.alac', '.ogg', '.opus', '.wma', '.wv', '.ape',
    '.m4a', '.mp4', '.mov', '.amr', '.ac3', '.dts', '.mka',
    '.spx', '.ra', '.au', '.snd', '.caf', '.tta', '.gsm'
]

IN_DIR = Path('.').resolve()


def collect_audio_stats(root, extensions):
    total = 0
    per_ext = Counter()
    per_folder = defaultdict(int)
    subfolders = set()
    name_map = defaultdict(list)

    for rel_path in find_audio_files(root):
        if rel_path.suffix.lower() not in extensions:
            continue
        total += 1
        ext = rel_path.suffix.lower()
        per_ext[ext] += 1
        folder = str(rel_path.parent)
        if folder and folder != ".":
            subfolders.add(folder)
        per_folder[folder] += 1
        name_ohne_ext = rel_path.stem
        name_map[name_ohne_ext].append(rel_path.as_posix())
    return total, per_ext, per_folder, subfolders, name_map


def main():
    total, per_ext, per_folder, subfolders, name_map = collect_audio_stats(
        IN_DIR, EXTENDED_EXTENSIONS)
    print(f"\nGefundene Audiodateien: {total}")
    print("\nDavon pro Dateityp:")
    for ext, count in per_ext.items():
        print(f"  {ext}: {count}")
    print(f"\nUnterschiedliche Unterordner (außer Root): {len(subfolders)}")
    for folder, count in per_folder.items():
        print(f"  {folder}: {count}")

    print("\nNamens-Dubletten (gleicher Name, unterschiedliche Endung oder Ordner):")
    found = False
    for name, paths in name_map.items():
        if len(paths) > 1:
            found = True
            print(f'  "{name}" in:')
            for p in paths:
                print(f"    {p}")
    if not found:
        print("  Keine Dubletten gefunden.")

    print()

if __name__ == "__main__":
    main()
