#!/usr/bin/env python3
# transcode.py
#
# Rekursive Test-CLI für lib.file.transcode():
# - Start: aktuelles Arbeitsverzeichnis (CWD)
# - Durchsucht den gesamten Baum nach Audio-Dateien (AUDIO_EXTENSIONS)
# - Spiegelt die Struktur nach STAGE_ROOT/transcode-<timestamp>/...
# - Optionen: --force-reencode, --report (JSON), --keep-temp, --dry-run
# - Fail-fast: Tools/IO werden vorab geprüft; Fehler führen zu Exit 1/2.

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from lib import config
from lib.file import transcode
from lib.utils import get_timestamp, find_audio_files


# --------- Hilfsfunktionen ---------

def _which_or_die(name: str) -> None:
    if shutil.which(name) is None:
        sys.stderr.write(
            f"Voraussetzung fehlt: {name} nicht gefunden (im PATH)\n")
        sys.exit(2)


def _ffprobe_json(src: Path) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(src)
    ])
    return json.loads(out.decode("utf-8"))


def _decide_mode(ffprobe_info: dict, force_reencode: bool) -> str:
    fmt_name = (ffprobe_info.get("format", {}) or {}).get("format_name", "")
    if "flac" in fmt_name and not force_reencode:
        return "COPY"
    return "REENC"


def _has_attached_pic(ffprobe_info: dict) -> bool:
    for s in ffprobe_info.get("streams", []):
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") == 1:
            return True
    return False


def _compute_out_path(stage_root: Path, ts: str, rel_src: Path) -> Path:
    # rel_src ist relativ zu CWD; Ziel immer .flac
    rel = rel_src
    if rel.suffix.lower() != ".flac":
        rel = rel.with_suffix(".flac")
    return stage_root / f"transcode-{ts}" / rel


def _write_json_report(out_path: Path, result: dict, dry_run: bool) -> None:
    report_path = out_path.with_suffix(out_path.suffix + ".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.copy()
    payload["dry_run"] = dry_run
    report_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")


# --------- Hauptprogramm ---------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Rekursiver Transcode ab Arbeitsverzeichnis → FLAC (Tags, Front-Cover, finaler Remux)."
    )
    ap.add_argument("--force-reencode", action="store_true",
                    help="Erzwingt Re-Encode auch bei FLAC (Debug/Edge-Tests)")
    ap.add_argument("--report", action="store_true",
                    help="Schreibt JSON-Report neben jede Zieldatei")
    ap.add_argument("--keep-temp", action="store_true",
                    help="Behält Zwischenartefakte in TEMP_ROOT/_debug")
    ap.add_argument("--dry-run", action="store_true",
                    help="Nur analysieren und geplante Aktionen anzeigen – nichts schreiben")

    args = ap.parse_args()

    # Preflight
    _which_or_die("ffmpeg")
    _which_or_die("ffprobe")

    cwd = Path.cwd()
    stage_root = Path(config.STAGE_ROOT)
    ts = get_timestamp()

    # Stage-Basis anlegbar?
    base_out_dir = stage_root / f"transcode-{ts}"
    base_out_dir.mkdir(parents=True, exist_ok=True)

    # Dateien ermitteln (Snapshot, relativ zu CWD)
    files = find_audio_files(
        cwd, absolute=False, filter_ext=config.AUDIO_EXTENSIONS)
    if not files:
        print("Keine kompatiblen Audiodateien gefunden.")
        sys.exit(0)

    total = len(files)
    errors = 0

    # Rekursive Verarbeitung
    for rel_path in files:
        src_path = cwd / rel_path
        out_path = _compute_out_path(stage_root, ts, rel_path)

        if args.dry_run:
            info = _ffprobe_json(src_path)
            mode = _decide_mode(info, args.force_reencode)
            has_pic = _has_attached_pic(info)
            cover_state = "original" if has_pic else "placeholder"

            actions = {
                "source_format": (info.get("format", {}) or {}).get("format_name", ""),
                "mode": "copy" if mode == "COPY" else "reencode",
                "tags_copied": True,           # geplant via -map_metadata 0
                "cover_added": cover_state,    # geplant
                "remuxed": True,               # immer
                "comment_touched": True,       # am Ende
            }
            result = {
                "src_path": str(src_path),
                "out_path": str(out_path),
                "actions": actions,
                "notes": "" if has_pic else "Kein Original-Cover, Platzhalter würde verwendet.",
            }

            if args.report:
                _write_json_report(out_path, result, dry_run=True)

            print(f"[DRY] {rel_path} → {out_path.relative_to(stage_root)} | mode={actions['mode'].upper()} | cover={actions['cover_added']} | remux=YES")
            continue

        # Echter Lauf
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Fehler durchschlagen lassen → Exit 1 am Ende, keine lokale try/except
        try:
            result = transcode(
                src_path=src_path,
                out_path=out_path,
                force_reencode=args.force_reencode,
                keep_temp=args.keep_temp,
            )
            result["src_path"] = str(src_path)

            if args.report:
                _write_json_report(out_path, result, dry_run=False)

            act = result["actions"]
            print(
                f"{rel_path} → {out_path.relative_to(stage_root)} | mode={act['mode'].upper()} | cover={act['cover_added']} | remux=YES")

        except Exception as e:
            errors += 1
            sys.stderr.write(f"FEHLER bei {src_path}: {e}\n")

    # Exit-Code je nach Fehlern
    if errors > 0:
        sys.stderr.write(
            f"Abgeschlossen mit Fehlern: {errors}/{total} Dateien fehlgeschlagen.\n")
        sys.exit(1)

    print(f"Erfolg: {total} Dateien verarbeitet.")
    sys.exit(0)


if __name__ == "__main__":
    main()
