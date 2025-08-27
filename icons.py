#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
icons_build_min.py
------------------
Scannt den aktuellen Ordner nach PNGs (nicht rekursiv),
legt im Elternordner einen versteckten Ordner "icons" an (Windows),
und erzeugt für jede PNG eine gleichnamige .ico mit Frames 64/128/256,
jeweils in sRGB, quadratisch, "cover"-Skalierung, zentriert, mit weißem
Hintergrund (kein Alpha), 8-Bit TrueColor, ohne Metadaten.

Früher Abbruch: Wenn ..\icons bereits existiert, macht das Skript nichts.
Voraussetzung: ImageMagick in PATH (bevorzugt 'magick', Fallback 'convert').
"""

from __future__ import annotations
import sys
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

SIZES = [64, 128, 256]


def find_im_binary() -> Optional[str]:
    """Bevorzuge 'magick' (IM7), sonst 'convert' (IM6)."""
    for candidate in ("magick", "convert"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def run_im(im_bin: str, args: List[str]) -> None:
    """
    Führt ImageMagick-Befehle robust aus (ohne Shell).
    args enthält Input(s), Optionen und Output-Datei.
    """
    cmd = [im_bin] + args
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ImageMagick-Fehler ({im_bin}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def im_norm_command(src: Path, dst: Path, size: int) -> List[str]:
    """
    Erzeugt die Argumente für die Frame-Normierung:
    - sRGB
    - cover-Resize auf size x size mit zentralem Zuschnitt/Erweiterung
    - weißer Hintergrund
    - Alpha AUS / flach gerechnet
    - 8-Bit TrueColor, keine Metadaten
    """
    # WICHTIG: Wir passen src/dst als Strings ein; keine Shell nötig.
    return [
        str(src),
        "-colorspace", "sRGB",
        "-resize", f"{size}x{size}^",
        "-gravity", "center",
        "-background", "white",
        "-extent", f"{size}x{size}",
        "-alpha", "off",
        "-flatten",
        "-depth", "8",
        "-type", "TrueColor",
        "-define", "png:color-type=2",
        "-strip",
        str(dst),
    ]


def im_ico_command(frames: List[Path], dst_ico: Path) -> List[str]:
    """
    Baut das .ico aus den vorbereiteten PNG-Frames.
    Beibehaltung sRGB, 8-Bit, TrueColor, Alpha off.
    """
    return (
        [str(p) for p in frames]
        + [
            "-colorspace", "sRGB",
            "-alpha", "off",
            "-depth", "8",
            "-type", "TrueColor",
            str(dst_ico),
        ]
    )


def set_hidden_windows(path: Path) -> None:
    """Markiert einen Ordner unter Windows als 'Hidden'."""
    if platform.system().lower() != "windows":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        GetFileAttributesW.restype = ctypes.c_uint32
        SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        SetFileAttributesW.restype = ctypes.c_int

        attrs = GetFileAttributesW(str(path))
        if attrs == 0xFFFFFFFF:
            return  # konnte nicht lesen; still ignorieren
        new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN
        SetFileAttributesW(str(path), new_attrs)
    except Exception:
        # Fallback still: ignorieren, wenn Hidden nicht gesetzt werden kann
        pass


def main() -> int:
    cwd = Path.cwd()
    parent = cwd.parent
    icons_dir = parent / "icons"

    print(f"[INFO] Aktueller Ordner: {cwd}")
    print(f"[INFO] Zielordner: {icons_dir}")

    # Früher Abbruch, wenn icons bereits existiert
    if icons_dir.exists():
        print(
            "[INFO] 'icons' existiert bereits im Elternordner. Früher Abbruch – nichts zu tun.")
        return 0

    # ImageMagick suchen
    im_bin = find_im_binary()
    if not im_bin:
        print("[ERROR] ImageMagick ('magick' oder 'convert') wurde nicht im PATH gefunden.", file=sys.stderr)
        return 2
    print(f"[INFO] Verwende ImageMagick-Binärdatei: {im_bin}")

    # PNGs im aktuellen Ordner einsammeln (case-insensitive, nicht rekursiv)
    pngs = sorted([p for p in cwd.iterdir() if p.is_file()
                  and p.suffix.lower() == ".png"])
    if not pngs:
        print("[INFO] Keine PNG-Dateien im aktuellen Ordner gefunden. Nichts zu tun.")
        # icons-Ordner auch nicht anlegen, wenn es nichts zu tun gibt.
        return 0

    # icons anlegen (neu)
    try:
        icons_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # Rennen gewonnen? Egal — gemäß Spezifikation: früher Abbruch.
        print(
            "[INFO] 'icons' ist gerade entstanden (Race) – früher Abbruch ohne weitere Arbeit.")
        return 0

    # Unter Windows: icons verstecken
    set_hidden_windows(icons_dir)

    # temporäres Arbeitsverzeichnis (im aktuellen Ordner, damit Pfadlängen kurz bleiben)
    tmp_root = cwd / f".__icon_tmp_{uuid4().hex[:8]}"
    tmp_root.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0
    try:
        for src_png in pngs:
            base = src_png.stem
            # Zwischen-Frames vorbereiten
            frame_paths = [tmp_root / f"{base}_{s}_white.png" for s in SIZES]

            try:
                # 1) Frames normalisieren
                for size, frame in zip(SIZES, frame_paths):
                    args = im_norm_command(src_png, frame, size)
                    run_im(im_bin, args)

                # 2) ICO bauen (temporär + atomar ersetzen)
                dst_tmp = icons_dir / f".__tmp__{base}.ico"
                dst_final = icons_dir / f"{base}.ico"
                args_ico = im_ico_command(frame_paths, dst_tmp)
                run_im(im_bin, args_ico)

                # Atomar verschieben/ersetzen
                if dst_final.exists():
                    dst_final.unlink()
                dst_tmp.replace(dst_final)

                ok += 1
                print(
                    f"[OK]  {src_png.name}  →  {dst_final.relative_to(parent)}")
            except Exception as e:
                fail += 1
                print(f"[FAIL] {src_png.name}: {e}", file=sys.stderr)
            finally:
                # Frames aufräumen
                for f in frame_paths:
                    try:
                        if f.exists():
                            f.unlink()
                    except Exception:
                        pass
    finally:
        # tmp_root aufräumen
        try:
            for child in tmp_root.iterdir():
                try:
                    child.unlink()
                except Exception:
                    pass
            tmp_root.rmdir()
        except Exception:
            pass

    print(f"\n[SUMMARY] Erfolgreich: {ok}  |  Fehlgeschlagen: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
