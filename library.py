"""
library.py

Initialisiert und verwaltet die zentrale Ordnerstruktur deiner DJ-Suite.

- Mit `--touch` wird die gesamte Bibliotheksstruktur gemäß Konfiguration angelegt (wie bisher touch_lib.py).
- Ohne Option wird eine ausführliche Hilfeseite angezeigt.

Dies stellt sicher, dass alle notwendigen Arbeitsbereiche (ARCHIV, STAGE, WORKSPACE, BAG, TEMP, LOG, DB) existieren,
bevor du mit weiteren Schritten (Archivieren, Taggen, Transkodieren etc.) arbeitest.

Empfohlen als ersten Schritt nach dem Aufsetzen deiner DJ-Umgebung!

Autor: (dein Name)
Lizenz: MIT (anpassen, falls gewünscht)
"""

import argparse
import os
from lib.config import (
    LIBRARY_ROOT, ARCHIV_ROOT, STAGE_ROOT, WORKSPACE_ROOT,
    BAG_ROOT, TEMP_ROOT, LOG_ROOT, DB_NAME
)

def ensure_dir(path):
    """Legt den Ordner an, falls nicht vorhanden."""
    os.makedirs(path, exist_ok=True)
    print(f"[OK] {path}")

def ensure_db_folder(parent):
    """Lege DB-Unterordner unterhalb des Parent-Ordners an."""
    db_path = os.path.join(parent, DB_NAME)
    ensure_dir(db_path)

def touch_library():
    print("Erzeuge Library-Struktur (falls nicht vorhanden):")
    ensure_dir(LIBRARY_ROOT)
    ensure_dir(ARCHIV_ROOT)
    ensure_dir(STAGE_ROOT)
    ensure_dir(WORKSPACE_ROOT)
    ensure_dir(BAG_ROOT)
    ensure_dir(TEMP_ROOT)
    ensure_dir(LOG_ROOT)
    print("\nLege DB-Unterordner in allen Hauptbereichen an:")
    for parent in (ARCHIV_ROOT, STAGE_ROOT, WORKSPACE_ROOT, BAG_ROOT):
        ensure_db_folder(parent)
    print("\nFertig! Alle relevanten Ordner existieren jetzt.")

HELP_TEXT = """
library.py – DJ-Library-Manager

Mit diesem Tool richtest du die komplette Verzeichnisstruktur deiner DJ-Suite ein
(Archiv, Stage, Workspace, Bag, Log, Temp, DB-Unterordner). Das Skript liest die 
benötigten Pfade und Namen aus deiner zentralen Konfigurationsdatei (djs-config.yaml).

Aufruf:

  python library.py --touch

Optionen:
  --touch      Lege alle erforderlichen Ordner (Library-Root, Archiv, Stage, Workspace,
               Bag, Log, Temp) sowie DB-Unterordner in den Hauptbereichen an.

Ohne Optionen wird diese Hilfeseite angezeigt.

Typische Workflows:
- Führe dieses Skript immer dann aus, wenn du die Library-Struktur erstmalig aufsetzen
  oder nach einer Änderung an der Konfiguration aktualisieren willst.
- Anschließend kannst du mit den eigentlichen Arbeits-Skripten (Archivieren, Taggen,
  Transkodieren etc.) starten.

Alle Struktur-Definitionen werden aus lib/config.py geladen.
"""

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--touch', action='store_true', help="Lege alle erforderlichen Ordner an")
    args = parser.parse_args()

    if args.touch:
        touch_library()
    else:
        print(HELP_TEXT)

if __name__ == "__main__":
    main()

