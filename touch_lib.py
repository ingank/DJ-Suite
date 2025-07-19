# touch_lib.py

from lib.config import (
    LIBRARY_ROOT, ARCHIV_ROOT, STAGE_ROOT, WORKSPACE_ROOT,
    BAG_ROOT, TEMP_ROOT, LOG_ROOT, DB_NAME
)
import os


def ensure_dir(path):
    """Legt den Ordner an, falls nicht vorhanden."""
    os.makedirs(path, exist_ok=True)
    print(f"[OK] {path}")


def ensure_db_folder(parent):
    """Lege DB-Unterordner unterhalb des Parent-Ordners an."""
    db_path = os.path.join(parent, DB_NAME)
    ensure_dir(db_path)


def main():
    print("Erzeuge Library-Struktur (falls nicht vorhanden):")
    ensure_dir(LIBRARY_ROOT)
    ensure_dir(ARCHIV_ROOT)
    ensure_dir(STAGE_ROOT)
    ensure_dir(WORKSPACE_ROOT)
    ensure_dir(BAG_ROOT)
    ensure_dir(TEMP_ROOT)
    ensure_dir(LOG_ROOT)

    print("Lege DB-Unterordner in allen Hauptbereichen an:")
    for parent in (ARCHIV_ROOT, STAGE_ROOT, WORKSPACE_ROOT, BAG_ROOT):
        ensure_db_folder(parent)
    print("\nFertig! Alle relevanten Ordner existieren jetzt.")


if __name__ == "__main__":
    main()
