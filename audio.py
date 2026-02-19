#!/usr/bin/env python3
"""audio.py – Zentrale Audiooperationen (Endformat: FLAC, Quelle: ".")"""

import argparse
import json
import sys
from pathlib import Path
from lib import flac, config
from lib.utils import get_timestamp, find_audio_files, collect_audio_stats, mirror_folder


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

    # remux: jetzt mit --mirror
    p_remux = sub.add_parser("remux", help="FLAC → FLAC (Blocklayout fix)")
    p_remux.add_argument(
        "--mirror",
        action="store_true",
        help="Nicht-FLACs per Robocopy spiegeln (Windows); FLACs werden remuxt.",
    )

    sub.add_parser("finalize",
                   help="FLAC → FLAC 24bit/44.1kHz (Workspace→Bag)")
    sub.add_parser("tagexport",
                   help="Exportiert alle Text-Tags aus .flac-Dateien"
                   "rekursiv ab aktuellem Verzeichnis "
                   "in eine NDJSON-Datei (audio-tagexport-<timestamp>.ndjson).")

    p_count = sub.add_parser(
        "count",
        help="Zählt Audiodateien rekursiv und zeigt Statistiken/Dubletten."
    )
    p_count.add_argument(
        "--ext",
        nargs="+",
        metavar="EXT",
        help="Erlaubte Dateiendungen (z. B. .flac .wav). Überschreibt KNOWN_AUDIO_EXTENSIONS.",
    )
    p_count.add_argument(
        "--json",
        action="store_true",
        help="Gibt die Statistik als JSON aus.",
    )
    p_count.add_argument(
        "--duplicates-only",
        action="store_true",
        help="Nur Dublettenliste ausgeben.",
    )
    p_count.add_argument(
        "--all-folders",
        action="store_true",
        help="Zeigt alle Ordner, auch ohne Treffer.",
    )
    grp_paths = p_count.add_mutually_exclusive_group()
    grp_paths.add_argument("--absolute", action="store_true",
                           help="Absolute Pfade in der Ausgabe.")
    grp_paths.add_argument("--relative", action="store_true",
                           help="Relative Pfade in der Ausgabe (Default).")

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

        # Optional: Non-FLACs spiegeln (Windows, Robocopy)
        if getattr(args, "mirror", False):
            try:
                mirror_folder(Path("."), out_root, exclude_exts=[
                              ".flac"], depth=args.depth)
                print("[mirror] Nicht-FLACs gespiegelt (Robocopy).")
            except Exception as e:
                print(f"[mirror][WARN] {e}")

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

    elif args.command == "count":
        # Endungen: Default KNOWN_AUDIO_EXTENSIONS; --ext überschreibt
        if args.ext:
            exts = {(e if e.startswith(".") else f".{e}").lower()
                    for e in args.ext}
        else:
            exts = set(config.KNOWN_AUDIO_EXTENSIONS)

        absolute = True if args.absolute and not args.relative else False

        stats = collect_audio_stats(
            root=".",
            extensions=exts,
            depth=args.depth,
            absolute=absolute,
            all_folders=args.all_folders,
        )

        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            return

        # Nur Dubletten?
        if args.duplicates_only:
            dups = stats.get("duplicates", {})
            print("[count] Dubletten:")
            if not dups:
                print("[count]   keine Dubletten gefunden")
            else:
                for name in sorted(dups.keys()):
                    print(f'  "{name}" in:')
                    for p in dups[name]:
                        print(f"    {p}")
            return

        # Menschliche Standardausgabe
        print(f"\n[count] gesamt: {stats['total']} Datei(en)")

        print("\n[count] pro Endung:")
        for ext, num in stats["per_ext"].items():
            print(f"  {ext:>6}: {num}")

        print("\n[count] pro Ordner:")
        if not stats["per_folder"]:
            print("  (keine Ordner)")
        else:
            for folder, num in stats["per_folder"].items():
                print(f"  {folder}: {num}")

        dups = stats.get("duplicates", {})
        print(f"\n[count] Dubletten-Gruppen: {len(dups)}")
        if dups:
            for name in sorted(dups.keys()):
                print(f'  "{name}" in:')
                for p in dups[name]:
                    print(f"    {p}")

        print()


if __name__ == "__main__":
    main()
