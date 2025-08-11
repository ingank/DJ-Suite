"""
bag.py

Exportiert alle Audiodateien aus WORKSPACE_ROOT in BAG_ROOT (flat),
konvertiert ins zentrale BAG_FORMAT und normalisiert auf das in der Konfig definierte LUFS-Ziel (BAG_LUFS).
Dateinamen im Bag sind immer der GEN0-SHA256-Tag der Quelldatei (keine Neuberechnung!).

Bricht ab, wenn auch nur eine Datei kein GEN0-SHA256-Tag oder keinen LUFS-Tag hat.
"""

import sys
import os
from pathlib import Path
from lib.config import WORKSPACE_ROOT, BAG_ROOT, BAG_LUFS
from lib.utils import find_audio_files
from lib.file import get_tags, touch_comment_tag, to_bag


def check_tauglichkeit(files):
    """
    Prüft, ob jede Datei GEN0-SHA256- und LUFS-Tag besitzt.
    Gibt Liste untauglicher Files (mit fehlendem Tag) zurück.
    """
    untauglich = []
    for f in files:
        tags = get_tags(f, ["gen0-sha256", "lufs"])
        if not tags["gen0-sha256"] or not tags["lufs"]:
            untauglich.append((f, tags))
    return untauglich


def main():
    files = [Path(WORKSPACE_ROOT).resolve() /
             rel for rel in find_audio_files(WORKSPACE_ROOT)]
    if not files:
        print(f"[INFO] Keine Audiodateien in {WORKSPACE_ROOT} gefunden.")
        sys.exit(0)

    untauglich = check_tauglichkeit(files)
    if untauglich:
        print("[ERROR] Es gibt untaugliche Dateien! Abbruch.")
        for f, tags in untauglich:
            missing = []
            if not tags["gen0-sha256"]:
                missing.append("GEN0-SHA256")
            if not tags["lufs"]:
                missing.append("LUFS")
            print(f"  {f} fehlt: {', '.join(missing)}")
        print(
            f"\n{len(untauglich)} Dateien sind nicht bag-tauglich. Vorgang abgebrochen!")
        sys.exit(1)

    print(
        f"[INFO] {len(files)} Dateien werden in den Bag exportiert (Target LUFS: {BAG_LUFS})")
    os.makedirs(BAG_ROOT, exist_ok=True)

    ok, err = 0, 0
    for f in files:
        tags = get_tags(f, ["gen0-sha256", "lufs"])
        sha = tags["gen0-sha256"]
        lufs = float(tags["lufs"])
        out_flac = Path(BAG_ROOT) / f"{sha}.flac"
        try:
            to_bag(
                src_flac=f,
                dst_flac=out_flac,
                src_lufs=lufs,
                target_lufs=BAG_LUFS
            )
            touch_comment_tag(out_flac)
            print(f"[OK] {f} → {out_flac} ({lufs:+.1f}dB → {BAG_LUFS:+.1f}dB)")
            ok += 1
        except Exception as e:
            print(f"[FEHLER] {f}: {e}")
            err += 1
    print(f"\n[INFO] {ok} Dateien erfolgreich baggiert, {err} Fehler.")


if __name__ == "__main__":
    main()
