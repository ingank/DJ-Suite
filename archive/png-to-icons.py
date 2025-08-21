#!/usr/bin/env python3
from __future__ import annotations
import csv
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Erwartete Größen-Spalten im Manifest:
#   source, out_256, out_128, out_64
EXPECTED_SIZES = [64, 128, 256]  # aufsteigend
MANIFEST_NAME = "manifest.csv"
ICON_PREFIX = "icons"


def find_im_binary() -> list[str]:
    """Bevorzugt IM7 ('magick'), fällt auf IM6 ('convert') zurück."""
    for cand in ("magick", "magick.exe"):
        if shutil.which(cand):
            return [cand]
    for cand in ("convert", "convert.exe"):
        if shutil.which(cand):
            return [cand]
    sys.exit(
        "Fehler: ImageMagick nicht gefunden (weder 'magick' noch 'convert' im PATH).")


def timestamp_folder(prefix: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    p = Path(f"{prefix}-{ts}")
    p.mkdir(parents=True, exist_ok=False)
    return p


def parse_headers_case_insensitive(reader: csv.DictReader) -> dict[str, str]:
    """Mappt erwartete Spaltennamen (lowercase) auf die tatsächlichen Header aus dem CSV."""
    headers = {h.lower(): h for h in (reader.fieldnames or [])}
    need = ["source", "out_256", "out_128", "out_64"]
    missing = [n for n in need if n not in headers]
    if missing:
        sys.exit(
            f"Fehler im Manifest-Header. Erwartet: {', '.join(need)}. Gefunden: {reader.fieldnames}")
    return {n: headers[n] for n in need}


def ensure_unique_path(p: Path) -> Path:
    """Falls Datei existiert, hänge -1, -2, ... an den Namen an."""
    if not p.exists():
        return p
    base, ext = p.stem, p.suffix
    i = 1
    while True:
        cand = p.with_name(f"{base}-{i}{ext}")
        if not cand.exists():
            return cand
        i += 1


def build_im_ico_cmd(im_bin: list[str], inputs: list[Path], output_ico: Path) -> list[str]:
    """
    Erzeuge den IM-Aufruf für ICO.
    - Farben/Depth vereinheitlichen
    - alpha off/TrueColor für maximale Kompatibilität
    """
    cmd = im_bin[:] + [str(p) for p in inputs]
    cmd += [
        "-colorspace", "sRGB",
        "-depth", "8",
        "-alpha", "off",
        "-type", "TrueColor",
        str(output_ico),
    ]
    return cmd


def main():
    cwd = Path(".").resolve()
    manifest_path = cwd / MANIFEST_NAME
    if not manifest_path.exists():
        sys.exit(
            f"Abbruch: '{MANIFEST_NAME}' nicht im aktuellen Ordner gefunden: {cwd}")

    im_bin = find_im_binary()
    out_dir = timestamp_folder(ICON_PREFIX)
    icons_manifest = out_dir / "icons_manifest.csv"

    successes, warnings = 0, 0

    with open(manifest_path, "r", newline="", encoding="utf-8") as f_in, \
            open(icons_manifest, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        header_map = parse_headers_case_insensitive(reader)
        writer = csv.writer(f_out)
        writer.writerow(["source", "ico", "used_sizes"])  # z. B. "64;128;256"

        rows = list(reader)
        if not rows:
            sys.exit("Abbruch: Manifest enthält keine Zeilen.")

        for row in rows:
            src_name = (row.get(header_map["source"]) or "").strip()
            if not src_name:
                print("[WARN] Leerer 'source'-Eintrag – Zeile übersprungen.")
                warnings += 1
                continue

            # ICO-Dateiname vom Original ableiten (ohne Endung)
            base = Path(src_name).stem

            # Pfade zu vorbereiteten PNGs (relativ zum aktuellen Ordner)
            size_to_field = {
                256: (row.get(header_map["out_256"]) or "").strip(),
                128: (row.get(header_map["out_128"]) or "").strip(),
                64:  (row.get(header_map["out_64"]) or "").strip(),
            }

            inputs: list[tuple[int, Path]] = []
            for s in EXPECTED_SIZES:
                rel = size_to_field.get(s) or ""
                if not rel:
                    continue
                p = (cwd / rel).resolve()
                if p.exists():
                    inputs.append((s, p))
                else:
                    print(f"[WARN] Datei fehlt (Manifest-Eintrag): {rel}")
                    warnings += 1

            if not inputs:
                print(
                    f"[WARN] Keine verwertbaren PNGs für '{src_name}'. Übersprungen.")
                warnings += 1
                continue

            # aufsteigend nach Größe
            inputs.sort(key=lambda t: t[0])
            input_paths = [p for _, p in inputs]

            out_ico = ensure_unique_path(out_dir / f"{base}.ico")
            cmd = build_im_ico_cmd(im_bin, input_paths, out_ico)

            try:
                subprocess.run(cmd, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                print(
                    f"[FEHLER] ICO-Build für '{base}' fehlgeschlagen:\n{e.stderr.decode(errors='ignore')[:800]}")
                continue

            used_sizes = ";".join(str(s) for s, _ in inputs)
            writer.writerow([src_name, out_ico.name, used_sizes])
            print(f"[OK] {src_name} → {out_ico}  (Größen: {used_sizes})")
            successes += 1

    print("\nZusammenfassung:")
    print(f"  Erfolgreich: {successes}")
    print(f"  Warnungen:   {warnings}")
    print(f"\nAusgabeordner: {out_dir.resolve()}")
    print(f"Icons-Manifest: {icons_manifest.resolve()}")


if __name__ == "__main__":
    main()
