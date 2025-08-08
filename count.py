"""
count.py

Zählt alle gängigen Audiodateien im aktuellen Ordner und in allen Unterordnern
und gibt zusätzliche Statistik aus (auch Dubletten).
"""

from pathlib import Path
from collections import Counter, defaultdict
from lib.utils import find_audio_files
from lib.config import EXTENDED_AUDIO_EXTENSIONS

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
        IN_DIR, EXTENDED_AUDIO_EXTENSIONS)
    print(f"\nGefundene Audiodateien: {total}")
    print("\nDavon pro Dateityp:")
    for ext, count in per_ext.items():
        print(f"  {ext}: {count}")

    print(f"\nUnterschiedliche Unterordner (außer Root): {len(subfolders)}")
    for folder in sorted(per_folder):
        # Alle Dateien im Ordner filtern
        ext_counts = Counter()
        for rel_path in name_map.values():
            for path in rel_path:
                if Path(path).parent == Path(folder):
                    ext = Path(path).suffix.lower()
                    ext_counts[ext] += 1
        # Ausgabe formatieren
        ext_summary = "; ".join(
            f"{ext}: {count}" for ext, count in ext_counts.items())
        print(f"  {folder}: {ext_summary}")

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
