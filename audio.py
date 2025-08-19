#!/usr/bin/env python3
"""audio.py – Zentrale Audiooperationen (Endformat: FLAC, Quelle: ".")"""

import argparse
import sys
from pathlib import Path
from lib import flac, config
from lib.utils import get_timestamp, find_audio_files


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="audio.py",
        description="Audio-Operationen: encode | remux | finalize",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximale Suchtiefe ab '.' (Standard: unbegrenzt)",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("encode", help="bekanntes Format → FLAC (Archiv→Stage)")
    sub.add_parser("remux", help="FLAC → FLAC (Blocklayout fix)")
    sub.add_parser("finalize",
                   help="FLAC → FLAC 24bit/44.1kHz (Workspace→Bag)")
    sub.add_parser("tagexport",
                   help="Exportiert alle Text-Tags aus .flac-Dateien"
                   "rekursiv ab aktuellem Verzeichnis "
                   "in eine NDJSON-Datei (audio-tagexport-<timestamp>.ndjson).")

    args = parser.parse_args()

    if args.command == "encode":
        # Zielwurzel: STAGE_ROOT/audio-encode-<timestamp>
        out_root = Path(config.STAGE_ROOT) / f"audio-encode-{get_timestamp()}"
        out_root.mkdir(parents=True, exist_ok=True)
        exts = config.KNOWN_AUDIO_EXTENSIONS

        files = find_audio_files(
            ".", absolute=True, depth=args.depth, filter_ext=exts)
        if not files:
            raise SystemExit("keine passenden Dateien gefunden")

        cwd = Path(".").resolve()
        stats = {"ok": 0}

        for src in files:
            src_path = Path(src)
            rel = src_path.resolve().relative_to(cwd)
            print(f"[audio encode] {rel}")

            # Zielpfad: Struktur unterhalb '.' spiegeln, Endformat: .flac
            dst_rel = rel.with_suffix(".flac")
            dst_path = out_root / dst_rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # encode bricht bei Fehlern selbst ab
            flac.encode(src_path, dst_path, rel_source_path=str(rel))
            stats["ok"] += 1

        print(f"[audio encode] fertig: ok={stats['ok']}")

    elif args.command == "remux":
        out_root = Path(config.STAGE_ROOT) / f"audio-remux-{get_timestamp()}"
        out_root.mkdir(parents=True, exist_ok=True)

        exts = {".flac"}
        files = find_audio_files(
            ".", absolute=True, depth=args.depth, filter_ext=exts)
        if not files:
            raise SystemExit("keine .flac-Dateien gefunden")

        cwd = Path(".").resolve()
        stats = {"ok": 0}

        for src in files:
            src_path = Path(src)
            rel = src_path.resolve().relative_to(cwd)
            print(f"[audio-remux] {rel}")

            dst_rel = rel.with_suffix(".flac")
            dst_path = out_root / dst_rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            flac.remux(src_path, dst_path, rel_source_path=str(rel))
            stats["ok"] += 1

        print(f"[remux] fertig: ok={stats['ok']}")

    # audio.py (Ausschnitt im CLI-Handler)

    elif args.command == "finalize":
        """
        finalize:
        - Ziel: FLAC 24-bit / 44.1 kHz, Dateiname <MX-HASH>.flac
        - Preflight: prüft, ob alle Eingangsdateien MX-HASH und MX-LUFS besitzen
                    und ob keine Hash-Dubletten vorkommen.
        - Bei Erfolg: ruft lib.flac.finalize() für jede Datei auf
        - Output: STAGE_ROOT/audio-finalize-<timestamp>
        """

        files = find_audio_files(".", filter_ext=[".flac"])

        if not files:
            print("[finalize] keine FLAC-Dateien gefunden")
            sys.exit(1)

        # Preflight
        print(f"[finalize] Preflight-Check für {len(files)} Dateien ...")

        lufs_map = {}
        hash_map = {}

        for f in files:
            tags = flac.get_tags(f, ["MX-LUFS", "MX-HASH"])
            mx_lufs = tags.get("MX-LUFS")
            mx_hash = tags.get("MX-HASH")

            if not mx_lufs:
                raise RuntimeError(f"MX-LUFS fehlt in: {f}")
            if not mx_hash:
                raise RuntimeError(f"MX-HASH fehlt in: {f}")

            try:
                float(mx_lufs)
            except Exception:
                raise RuntimeError(
                    f"MX-LUFS ungültig in: {f} (wert={mx_lufs})")

            if mx_hash in hash_map:
                raise RuntimeError(
                    f"Doppelter MX-HASH {mx_hash} in {f} und {hash_map[mx_hash]}"
                )

            lufs_map[f] = float(mx_lufs)
            hash_map[mx_hash] = f

        # Zielordner erzeugen
        out_root = Path(config.STAGE_ROOT) / \
            f"audio-finalize-{get_timestamp()}"
        out_root.mkdir(parents=True, exist_ok=True)
        print(f"[finalize] Output-Ordner: {out_root}")

        # Verarbeitung
        for f in files:
            mx_hash = flac.get_tags(f, ["MX-HASH"])["MX-HASH"].strip()
            out_path = out_root / f"{mx_hash}.flac"

            print(f"[finalize] {f} → {out_path}")
            info = flac.finalize(src_path=f, out_path=out_path)

            # Laufzeit-Feedback
            gain_db = info["actions"]["gain_db"]
            print(
                f"  [ok] mode={info['actions']['mode']}, "
                f"gain={gain_db:+.2f} dB, "
                f"rate={info['actions']['target_rate_hz']} Hz, "
                f"bits={info['actions']['target_bits_per_sample']}"
            )

        print("[finalize] abgeschlossen.")

    elif args.command == "tagexport":
        import json
        from mutagen.flac import FLAC

        # 1) Zieldatei vorbereiten
        out_path = Path(f"./audio-tagexport-{get_timestamp()}.ndjson")
        print(f"[tagexport] schreibe nach {out_path}")

        # 2) FLAC-Dateien rekursiv (relativ) sammeln
        files = find_audio_files(".", absolute=False, filter_ext=[".flac"])
        if not files:
            print("[tagexport] keine .flac-Dateien gefunden")
            raise SystemExit(0)

        written = 0
        skipped = 0

        with out_path.open("w", encoding="utf-8", newline="\n") as out_f:
            for rel in files:
                rel_path = Path(rel)
                try:
                    # 3) Tags via mutagen lesen (roh, ohne eigenes Wrapper-API)
                    audio = FLAC(str(rel_path))
                    # mutagen liefert dict(tag -> list[str]); wir normalisieren Keys auf lowercase
                    # und erzwingen List[str]-Werte
                    raw = dict(audio)
                    tags = {}
                    for k, v in raw.items():
                        key = str(k).lower()
                        if isinstance(v, (list, tuple)):
                            vals = [str(x) for x in v if x is not None]
                        elif v is None:
                            vals = []
                        else:
                            vals = [str(v)]
                        tags[key] = vals

                    # 4) NDJSON-Zeile schreiben
                    rec = {"path": rel_path.as_posix(), "tags": tags}
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1

                    # optional: leichtes Laufzeitfeedback
                    if written % 100 == 0:
                        print(f"[tagexport] {written} geschrieben …")

                except Exception as e:
                    print(f"[tagexport][WARN] überspringe {rel_path}: {e}")
                    skipped += 1
                    continue

        print(
            f"[tagexport] fertig: {written} Datei(en) exportiert, {skipped} übersprungen")


if __name__ == "__main__":
    main()
