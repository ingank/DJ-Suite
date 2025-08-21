#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import csv
import sys

# --- Konfiguration ---
SIZES = [256, 128, 64]   # Zielgrößen (Quadrate)
STRIP_METADATA = True    # Metadaten entfernen
FORCE_TRUECOLOR = True   # PNG ohne Alpha/Palette erzwingen
COLORTYPE_TRUECOLOR = "2"  # 2 = Truecolor (RGB, ohne Alpha) für png:color-type
BACKGROUND = "white"     # Hintergrundfarbe
# ----------------------


def find_im_binary() -> list[str]:
    """
    Findet den richtigen ImageMagick-Binary-Aufruf.
    Bevorzugt IM7 ('magick'), fällt auf IM6 ('convert') zurück.
    Gibt die argv-List des Programms zurück.
    """
    for cand in ("magick", "magick.exe"):
        if shutil.which(cand):
            return [cand]
    # Fallback für IM6:
    for cand in ("convert", "convert.exe"):
        if shutil.which(cand):
            return [cand]
    sys.exit("Fehler: ImageMagick nicht gefunden. Bitte 'magick' (IM7) oder 'convert' (IM6) im PATH bereitstellen.")


def timestamp_folder(prefix: str = "normalize") -> Path:
    # Timestamp in lokaler Zeit (einfach): YYYY-MM-DD_HH-MM-SS
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    p = Path(f"{prefix}-{ts}")
    p.mkdir(parents=True, exist_ok=False)
    return p


def build_im_command(im_bin: list[str], src: Path, dst: Path, size: int) -> list[str]:
    """
    Baut den ImageMagick-Aufruf.
    Ziel: proportional einpassen, auf NxN zentrieren, Weiß auffüllen,
          Transparenz entfernen, sRGB, 8-Bit TrueColor, Metadaten strippen.
    Reihenfolge der Operatoren ist bei IM wichtig.
    """
    cmd = im_bin[:]  # ['magick'] oder ['convert']

    # IM7: "magick input ... output"
    # IM6: "convert input ... output"
    cmd += [
        str(src),

        # 1) Sicherstellen, dass wir in sRGB arbeiten (konsistentes Rendering in Windows)
        "-colorspace", "sRGB",

        # 2) Proportional einpassen in die Zielbox (ohne Zuschneiden)
        #    z.B. 300x200 -> 256x171;  dann mit extent auf 256x256 erweitern.
        "-resize", f"{size}x{size}",

        # 3) Hintergrund weiß (für Extent & Flatten)
        "-background", BACKGROUND,
        "-gravity", "center",
        "-extent", f"{size}x{size}",

        # 4) Alle Ebenen gegen Weiß zusammenführen (falls Alpha/Layers vorhanden)
        "-flatten",

        # 5) 8-Bit/Kanal
        "-depth", "8",
    ]

    # 6) TrueColor erzwingen (keine Palette, kein Alpha)
    if FORCE_TRUECOLOR:
        # -alpha off stellt sicher, dass kein Alphakanal im Ergebnis landet.
        cmd += ["-alpha", "off", "-type", "TrueColor"]
        # png:color-type=2 == Truecolor (RGB ohne Alpha)
        cmd += ["-define", f"png:color-type={COLORTYPE_TRUECOLOR}"]

    # 7) Metadaten entfernen
    if STRIP_METADATA:
        cmd += ["-strip"]

    # 8) Zielpfad
    cmd += [str(dst)]
    return cmd


def process_pngs():
    im_bin = find_im_binary()
    out_dir = timestamp_folder("normalize")

    # Optional: Manifest
    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        writer.writerow(["source", "out_256", "out_128", "out_64"])

        pngs = sorted(Path(".").glob("*.png"))
        if not pngs:
            print("Keine PNGs im aktuellen Ordner gefunden.")
            return

        for src in pngs:
            base = src.stem
            row = [src.name]

            for size in SIZES:
                dst = out_dir / f"{base}_{size}_white.png"
                cmd = build_im_command(im_bin, src, dst, size)
                try:
                    subprocess.run(
                        cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except subprocess.CalledProcessError as e:
                    print(f"[FEHLER] {src} @ {size}px:",
                          e.stderr.decode(errors="ignore")[:500])
                    # Im Fehlerfall trotzdem Platzhalter in Manifest
                    row.append("")
                else:
                    row.append(dst.name)
                    print(
                        f"[OK] {src.name} -> {dst.relative_to(out_dir.parent)}")

            writer.writerow(row)

    print(f"\nFertig. Ausgabeordner: {out_dir.resolve()}")
    print(f"Manifest: {manifest_path.resolve()}")


if __name__ == "__main__":
    process_pngs()
