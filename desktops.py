#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
desktop_ini_tool.py
-------------------
Rekursiv ab aktuellem Ordner:
  • nicht-versteckte Ordner verarbeiten (Startordner selbst wird NICHT verarbeitet)
  • vorhandene desktop.ini löschen
  • neue desktop.ini schreiben mit IconResource = (..\\ * depth) + "icons\\<Ordnername>.ico,0"
  • desktop.ini auf Hidden+System setzen, Ordner auf ReadOnly setzen
"""

from __future__ import annotations
import os
import sys
import platform
from pathlib import Path
import ctypes
from ctypes import wintypes
import tempfile
from typing import List

IS_WINDOWS = platform.system().lower() == "windows"

# Windows-Attribute
FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_HIDDEN = 0x00000002
FILE_ATTRIBUTE_SYSTEM = 0x00000004
FILE_ATTRIBUTE_NORMAL = 0x00000080

# WinAPI (nur auf Windows)


class WinAPI:
    def __init__(self) -> None:
        k32 = ctypes.windll.kernel32
        self.GetFileAttributesW = k32.GetFileAttributesW
        self.SetFileAttributesW = k32.SetFileAttributesW
        self.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        self.GetFileAttributesW.restype = wintypes.DWORD
        self.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        self.SetFileAttributesW.restype = wintypes.BOOL


WIN = WinAPI() if IS_WINDOWS else None


def get_attrs(path: Path) -> int:
    if not IS_WINDOWS:
        return 0
    attrs = WIN.GetFileAttributesW(str(path))
    return int(attrs)


def set_attrs(path: Path, attrs: int) -> None:
    if not IS_WINDOWS:
        return
    WIN.SetFileAttributesW(str(path), attrs)


def add_attrs(path: Path, flags: int) -> None:
    if not IS_WINDOWS:
        return
    current = get_attrs(path)
    if current == 0xFFFFFFFF:
        return
    set_attrs(path, current | flags)


def remove_attrs(path: Path, flags: int) -> None:
    if not IS_WINDOWS:
        return
    current = get_attrs(path)
    if current == 0xFFFFFFFF:
        return
    set_attrs(path, current & ~flags)


def is_hidden_dir(path: Path) -> bool:
    name = path.name
    if name in (".", ""):
        return False
    # dot-folders immer ignorieren
    if name.startswith("."):
        return True
    if IS_WINDOWS:
        attrs = get_attrs(path)
        if attrs != 0xFFFFFFFF and (attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)):
            return True
    return False


def is_icons_dir(path: Path) -> bool:
    return path.name.lower() == "icons"


def compute_iconresource(start_dir: Path, folder: Path) -> str:
    """
    IconResource = '..\\' * depth + 'icons\\' + '<FolderName>.ico,0'
    depth = Ebenen von start_dir zu folder (start_dir selbst => depth=0)
    """
    rel = os.path.relpath(folder, start_dir)  # '.' oder 'A\\B'
    depth = 0 if rel == "." else len(Path(rel).parts)
    prefix = "..\\" * depth            # << korrigiert: kein +1 mehr
    return f"{prefix}icons\\{folder.name}.ico,0"


def delete_existing_desktop_ini(folder: Path) -> None:
    ini = folder / "desktop.ini"
    if ini.exists():
        if IS_WINDOWS:
            # ggf. Hidden/System/Readonly entfernen
            set_attrs(ini, FILE_ATTRIBUTE_NORMAL)
        try:
            ini.unlink()
        except Exception:
            if IS_WINDOWS:
                set_attrs(ini, FILE_ATTRIBUTE_NORMAL)
            ini.unlink()


def write_desktop_ini(folder: Path, iconresource: str) -> None:
    ini = folder / "desktop.ini"
    content = (
        "[.ShellClassInfo]\n"
        f"IconResource={iconresource}\n"
        "[ViewState]\n"
        "FolderType=Music\n"
    )

    # atomar schreiben
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(folder), delete=False) as tf:
        tmp_path = Path(tf.name)
        tf.write(content)

    if ini.exists():
        if IS_WINDOWS:
            set_attrs(ini, FILE_ATTRIBUTE_NORMAL)
        ini.unlink(missing_ok=True)

    tmp_path.replace(ini)

    if IS_WINDOWS:
        set_attrs(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
        add_attrs(folder, FILE_ATTRIBUTE_READONLY)


def walk_non_hidden(start_dir: Path) -> List[Path]:
    """
    os.walk ab start_dir, aber:
      - versteckte Ordner (Hidden/System/dot) nicht traversieren
      - 'icons' überspringen
      - den Startordner NICHT in die Ergebnisliste aufnehmen
    """
    result: List[Path] = []
    for root, dirs, _files in os.walk(start_dir):
        root_path = Path(root)

        # Subdirs filtern (IN-PLACE)
        keep = []
        for d in dirs:
            p = root_path / d
            if is_icons_dir(p) or is_hidden_dir(p):
                continue
            keep.append(d)
        dirs[:] = keep

        # Startordner NICHT aufnehmen
        if root_path == start_dir:
            continue
        # sonstigen versteckten/icons-Ordner nicht aufnehmen
        if is_icons_dir(root_path) or is_hidden_dir(root_path):
            continue

        result.append(root_path)
    return result


def main() -> int:
    start_dir = Path.cwd()
    print(f"[INFO] Start: {start_dir}")
    if not start_dir.is_dir():
        print("[ERROR] Startpfad ist kein Ordner.", file=sys.stderr)
        return 2

    folders = walk_non_hidden(start_dir)
    print(f"[INFO] Zu verarbeitende Ordner (ohne Startordner): {len(folders)}")

    ok = 0
    fail = 0
    for folder in folders:
        try:
            iconresource = compute_iconresource(start_dir, folder)
            delete_existing_desktop_ini(folder)
            write_desktop_ini(folder, iconresource)
            ok += 1
            rel = folder.relative_to(start_dir)
            print(f"[OK]  {rel}\\desktop.ini → IconResource={iconresource}")
        except Exception as e:
            fail += 1
            print(f"[FAIL] {folder}: {e}", file=sys.stderr)

    print(
        f"\n[SUMMARY] desktop.ini neu geschrieben: {ok}  |  Fehlgeschlagen: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
