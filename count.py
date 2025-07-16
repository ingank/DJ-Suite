"""
count.py

Zählt alle Audiodateien im aktuellen Ordner und in allen Unterordnern
und gibt zusätzliche Statistik aus.
"""

import os
from pathlib import Path
from collections import Counter, defaultdict

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.mp3', '.flac', '.aifc']
IN_DIR = Path('.').resolve()


def collect_audio_stats(root):
    total = 0
    per_ext = Counter()
    per_folder = defaultdict(int)
    subfolders = set()

    for dirpath, _, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            subfolders.add(rel_dir)
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in AUDIO_EXTENSIONS:
                total += 1
                per_ext[ext] += 1
                per_folder[rel_dir] += 1

    return total, per_ext, per_folder, subfolders


def main():
    total, per_ext, per_folder, subfolders = collect_audio_stats(IN_DIR)
    print(f"\nGefundene Audiodateien: {total}")
    print("Davon pro Dateityp:")
    for ext, count in per_ext.items():
        print(f"  {ext}: {count}")
    print(f"Unterschiedliche Unterordner (außer Root): {len(subfolders)}")
    # Optional ausführliche Ausgabe pro Ordner:
    # print("Dateien pro Unterordner:")
    for folder, count in per_folder.items():
        print(f"  {folder}: {count}")


if __name__ == "__main__":
    main()
