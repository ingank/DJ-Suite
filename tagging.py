#!/usr/bin/env python3
r"""
Tagging-Tool (Windows-only)

Subcommand: raw
  4-Phasen-Ablauf:
    1) FIND  : Alle .flac-Dateien rekursiv unter . finden
    2) READ  : vorhandene Tags (mx-genre) lesen
    3) PLAN  : Zielwert (Slug) berechnen → SET / UPDATE / SKIP klassifizieren
    4) WRITE : (nur mit --go) Tags tatsächlich schreiben; Hard-Break bei erstem Fehler

Regeln / Vorgaben:
  - Standardmodus ist --dry-run (nur planen, nichts schreiben)
  - --go aktiviert Phase 4
  - Keine Ordnerfilterung (keine Ausschlüsse), rekursiv über alle Ordner
  - Slug-Bildung:
      * Pro Pfad-Ebene: führenden numerischen Präfix + Leerzeichen entfernen (Regex ^\d+\s+)
      * Kleinschreibung
      * Leerzeichen → '_' (Unterstrich)
      * Ebenen werden mit '-' (Bindestrich) verbunden
      * Beispiel: ".\\001 Foo Bar\\020 Baz\\track.flac" → "foo_bar-baz"
  - Wenn mx-genre bereits exakt dem Ziel entspricht → NICHT erneut schreiben
  - Live-Logging (stdout, spülend) + paralleles Datei-Logging in .\\tagging-raw-<timestamp>.log (UTF-8)
  - Exit-Code: 0 = OK, 1 = Fehler (Hard-Break bei erstem Fehler in READ/PLAN/WRITE)

Hinweis: Dieses Skript verwendet 'mutagen' (pip install mutagen).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# --- Windows-only Guard -----------------------------------------------------
import platform
if platform.system() != "Windows":
    sys.stderr.write("Dieses Tool ist nur für Windows vorgesehen.\n")
    sys.exit(1)

# --- Try to import mutagen --------------------------------------------------
try:
    from mutagen.flac import FLAC  # type: ignore
except Exception as e:  # pragma: no cover
    sys.stderr.write(
        "Fehler: 'mutagen' ist nicht installiert oder lädt nicht. "
        "Bitte installieren: pip install mutagen\n"
    )
    sys.exit(1)

# --- Logging helper ---------------------------------------------------------


class DualLogger:
    def __init__(self, logfile: Path, verbose: bool = False) -> None:
        self.logfile = logfile
        self.verbose = verbose
        # Datei im UTF-8-Append-Modus öffnen
        self._fh = open(self.logfile, "a", encoding="utf-8", errors="replace")
        # Konsole auf UTF-8 konfigurieren (Windows 3.7+)
        try:
            # type: ignore[attr-defined]
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def _write(self, stream, msg: str) -> None:
        stream.write(msg)
        try:
            stream.flush()
        except Exception:
            pass

    def info(self, line: str) -> None:
        msg = line.rstrip("\n") + "\n"
        self._write(sys.stdout, msg)
        self._fh.write(msg)
        self._fh.flush()

    def debug(self, line: str) -> None:
        if self.verbose:
            self.info(line)

    def error(self, line: str) -> None:
        msg = line.rstrip("\n") + "\n"
        self._write(sys.stderr, msg)
        self._fh.write(msg)
        self._fh.flush()

# --- Utilities --------------------------------------------------------------


def timestamp_for_filename() -> str:
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


SLUG_PREFIX_RE = re.compile(r"^\d+\s+")


def make_slug_from_path(file_path: Path, root: Path) -> str:
    r"""Baue den mx-genre-Slug aus dem relativen Ordnerpfad ab 'root'.

    Regeln:
      - pro Ebene numerischen Präfix + Leerzeichen entfernen (^\d+\s+)
      - kleinschreiben
      - Leerzeichen → '_'
      - Ebenen mit '-' verbinden
    """
    rel = file_path.parent.relative_to(root)
    parts: List[str] = []
    for part in rel.parts:
        clean = SLUG_PREFIX_RE.sub("", part)
        clean = clean.lower().replace(" ", "_")
        parts.append(clean)
    return "-".join([p for p in parts if p])

# --- FLAC Tag I/O -----------------------------------------------------------


def read_mx_genre(flac_path: Path) -> Optional[str]:
    audio = FLAC(str(flac_path))
    # mutagen speichert Tags als Mapping: name -> list[str]
    for key in list(audio.keys()):
        if key.lower() == "mx-genre":
            vals = audio.get(key)
            if not vals:
                return None
            return vals[0]
    return None


def write_mx_genre(flac_path: Path, value: str) -> None:
    audio = FLAC(str(flac_path))
    audio["mx-genre"] = value
    audio.save()

# --- Phasen -----------------------------------------------------------------


@dataclass
class PlanItem:
    path: Path
    current: Optional[str]
    target: str
    action: str  # "SET" | "UPDATE" | "SKIP"


def phase_find(root: Path, logger: DualLogger) -> List[Path]:
    flacs: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        pdir = Path(dirpath)
        for name in filenames:
            if name.lower().endswith(".flac"):
                flacs.append(pdir / name)
    logger.info(f"[SCAN]   found {len(flacs)} FLAC(s)")
    return flacs


def phase_read(flacs: List[Path], root: Path, logger: DualLogger) -> List[Tuple[Path, Optional[str]]]:
    results: List[Tuple[Path, Optional[str]]] = []
    for f in flacs:
        rel = f.relative_to(root)
        try:
            val = read_mx_genre(f)
            shown = "-" if val is None else f'"{val}"'
            logger.info(f"[READ]   {rel}  mx-genre={shown}")
            results.append((f, val))
        except Exception as e:
            logger.error(f"[ERROR]  {rel}  READ: {e}")
            raise  # Hard-Break
    return results


def phase_plan(read_results: List[Tuple[Path, Optional[str]]], root: Path, logger: DualLogger) -> List[PlanItem]:
    plan: List[PlanItem] = []
    for f, current in read_results:
        target = make_slug_from_path(f, root)
        rel = f.relative_to(root)
        if current is None:
            logger.info(f"[PLAN]   {rel}  -> mx-genre=\"{target}\"")
            plan.append(PlanItem(f, current, target, "SET"))
        elif current == target:
            logger.info(f"[PLAN]   {rel}  mx-genre already \"{target}\"")
            plan.append(PlanItem(f, current, target, "SKIP"))
        else:
            logger.info(f"[PLAN]   {rel}  \"{current}\" -> \"{target}\"")
            plan.append(PlanItem(f, current, target, "UPDATE"))
    return plan


def phase_write(plan: List[PlanItem], root: Path, logger: DualLogger) -> Tuple[int, int]:
    set_count = 0
    update_count = 0
    for item in plan:
        if item.action == "SKIP":
            continue
        rel = item.path.relative_to(root)
        try:
            write_mx_genre(item.path, item.target)
            if item.action == "SET":
                set_count += 1
                logger.info(f"[SET]    {rel}  mx-genre=\"{item.target}\"")
            elif item.action == "UPDATE":
                update_count += 1
                logger.info(
                    f"[UPDATE] {rel}  \"{item.current}\" -> \"{item.target}\"")
        except Exception as e:
            logger.error(f"[ERROR]  {rel}  WRITE: {e}")
            raise  # Hard-Break
    return set_count, update_count

# --- CLI / Main -------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tagging.py",
        description=(
            "Taggt FLAC-Dateien mit dem Vorbis-Comment 'mx-genre' anhand des "
            "Ordnerpfads. Arbeitet rekursiv ab dem aktuellen Verzeichnis (.) "
            "ohne Ordnerausschlüsse."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_raw = sub.add_parser(
        "raw",
        help=(
            "Finde FLACs, lies Tags, plane Änderungen, schreibe Tags (mit --go)"
        ),
    )

    # mutually exclusive dry-run / go (default dry-run)
    mex = p_raw.add_mutually_exclusive_group()
    mex.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur planen & anzeigen, keine Dateien ändern (Standard)",
    )
    mex.add_argument(
        "--go",
        action="store_true",
        help="Änderungen tatsächlich schreiben (Phase 4 aktivieren)",
    )

    p_raw.add_argument(
        "--verbose",
        action="store_true",
        help="Detailliertere Live-Ausgabe",
    )

    return parser


def cmd_raw(args: argparse.Namespace) -> int:
    root = Path.cwd()

    # Standard = dry-run, wenn weder --dry-run noch --go angegeben
    dry_run = True if (not args.dry_run and not args.go) else args.dry_run

    log_name = f"tagging-raw-{timestamp_for_filename()}.log"
    logger = DualLogger(root / log_name, verbose=args.verbose)

    scanned = 0
    skipped = 0
    set_count_total = 0
    update_count_total = 0

    try:
        # Phase 1: FIND
        flacs = phase_find(root, logger)
        scanned = len(flacs)

        # Phase 2: READ (Hard-Break bei Fehler)
        read_results = phase_read(flacs, root, logger)

        # Phase 3: PLAN (Hard-Break nur, wenn slug-Berechnung fehlschlägt)
        plan = phase_plan(read_results, root, logger)
        skipped = sum(1 for it in plan if it.action == "SKIP")

        if dry_run:
            logger.info("---")
            logger.info(
                f"Scanned: {scanned}  Set: {sum(1 for it in plan if it.action == 'SET')}  "
                f"Updated: {sum(1 for it in plan if it.action == 'UPDATE')}  "
                f"Skipped: {skipped}  Errors: 0"
            )
            return 0

        # Phase 4: WRITE (nur mit --go), Hard-Break bei erstem Fehler
        set_count_total, update_count_total = phase_write(plan, root, logger)

        logger.info("---")
        logger.info(
            f"Scanned: {scanned}  Set: {set_count_total}  Updated: {update_count_total}  "
            f"Skipped: {skipped}  Errors: 0"
        )
        return 0

    except Exception:
        logger.info("---")
        logger.error(
            f"Scanned: {scanned}  Set: {set_count_total}  Updated: {update_count_total}  "
            f"Skipped: {skipped}  Errors: 1"
        )
        return 1
    finally:
        logger.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "raw":
        return cmd_raw(args)

    # Unreachable, da subparser required=True
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
