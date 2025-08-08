# library.py

import os
import sys
import lib.config as config


def check_structure():
    """
    Prüft, ob alle erwarteten Verzeichnisse existieren.
    Listet fehlende Verzeichnisse auf.
    """
    missing = []
    if not os.path.isdir(config.LIBRARY_ROOT):
        missing.append(config.LIBRARY_ROOT)
    for path in config.ALL_ROOT_DIRS:
        if not os.path.isdir(path):
            missing.append(path)

    if missing:
        print("Fehlende Verzeichnisse:")
        for m in missing:
            print("  -", m)
        sys.exit(1)
    else:
        print("Alle Verzeichnisse vorhanden.")


def main():
    if "--touch" in sys.argv:
        print("Erzeuge Verzeichnisstruktur...")
        config.create_directory_structure()
        print("Struktur erstellt.")
    else:
        print("Pruefe Verzeichnisstruktur...")
        check_structure()


if __name__ == "__main__":
    main()
