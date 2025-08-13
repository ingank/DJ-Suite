#!/usr/bin/env python3
"""audio.py – Zentrale Audiooperationen (Endformat: FLAC, Quelle: ".")"""

import argparse
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
    sub.add_parser(
        "finalize", help="FLAC → FLAC 24bit/44.1kHz (Workspace→Bag)")

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
        print("[remux] placeholder")

    elif args.command == "finalize":
        print("[finalize] placeholder")


if __name__ == "__main__":
    main()
