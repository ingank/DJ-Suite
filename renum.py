#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renum.py — Windows-only Renumbering Tool

Funktionen (nur Windows):
- Ordner oder Dateien nach Schema "<ZAHL> RESTNAME" bzw. "<ZAHL> RESTNAME.ext" umbenennen
- Null-gefüllt (konfigurierbare Breite), Start-/Schritt-Werte
- "folders" optional rekursiv mit globaler Sequenz (Preorder)
- Transaktional: Staging (-> .renum_tmp_*) und Commit, vollständiger Rollback bei Fehlern
- Windows-Verhalten:
  * Pfadausgabe im .\foo\bar Format (Backslashes)
  * Versteckte/System-Einträge werden ignoriert
  * Symbolische Links/Junctions werden übersprungen
  * Windows-Validierung (verbotene Zeichen, reservierte Basenamen, keine Endungen mit . oder Leerzeichen)
  * Sortierung wie bei Windows üblich: case-insensitiv, locale-basiert, stabil
- Lock-Verzeichnis .renum.lock verhindert Parallel-Läufe (wird zusätzlich als Hidden markiert)
"""

import argparse
import ctypes
import locale
import os
import re
import sys
import unicodedata
import uuid
from ctypes import wintypes
from typing import Dict, List, Optional, Tuple, Iterable

# ------------------------------------------------------------
# Windows-Only Guard
# ------------------------------------------------------------
if os.name != "nt":
    print("Dieses Tool ist ausschließlich für Microsoft Windows entwickelt und ausführbar.", file=sys.stderr)
    sys.exit(2)

# Für locale-basierte, case-insensitive Sortierung
try:
    locale.setlocale(locale.LC_COLLATE, "")
except locale.Error:
    pass

# ------------------------------------------------------------
# Windows Attribute & Helpers (Hidden/System)
# ------------------------------------------------------------
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
LOCK_DIR_NAME = ".renum.lock"

GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
GetFileAttributesW.restype = wintypes.DWORD

SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
SetFileAttributesW.restype = wintypes.BOOL


def get_file_attributes(path: str) -> Optional[int]:
    attrs = GetFileAttributesW(path)
    if attrs == 0xFFFFFFFF:
        return None
    return attrs


def is_hidden_or_system(path: str) -> bool:
    attrs = get_file_attributes(path)
    if attrs is None:
        return False
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


# ------------------------------------------------------------
# Windows-Name-Validierung
# ------------------------------------------------------------
INVALID_CHARS = set('<>:"/\\|?*')
RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_valid_windows_name(filename: str) -> bool:
    if not filename or filename.endswith(" ") or filename.endswith("."):
        return False
    if any(ch in INVALID_CHARS for ch in filename):
        return False
    base, _ext = os.path.splitext(filename)
    if base.upper() in RESERVED_BASENAMES:
        return False
    return True

# ------------------------------------------------------------
# Pfad- und Sortier-Helfer
# ------------------------------------------------------------


def relwin(path: str, base: str) -> str:
    rel = os.path.relpath(path, base)
    rel = rel.replace("/", "\\")
    if not rel.startswith(".\\") and not rel.startswith("..\\"):
        rel = ".\\" + rel
    return rel


def sort_key(name: str) -> str:
    return locale.strxfrm(name.casefold())


# ------------------------------------------------------------
# Name-Parsing & -Erzeugung
# ------------------------------------------------------------
PREFIX_RE = re.compile(r"^\s*(\d+)\s*(?:[.\-_]| {1,3})\s*", re.UNICODE)


def collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def strip_numeric_prefix(fullname: str, is_file: bool) -> Tuple[str, str]:
    """
    Entfernt führendes numerisches Präfix + Trenner.
    Dateien: nur Stammname prüfen (Extension bleibt).
    Rückgabe: (restname, extension) – für Ordner ist extension == "".
    """
    if is_file:
        stem, ext = os.path.splitext(fullname)
        m = PREFIX_RE.match(stem)
        if m:
            stem = stem[m.end():]
        stem = nfc(collapse_spaces(stem))
        return stem, ext
    else:
        name = fullname
        m = PREFIX_RE.match(name)
        if m:
            name = name[m.end():]
        name = nfc(collapse_spaces(name))
        return name, ""


def build_target_name(number: int, width: int, rest: str, ext: str = "") -> str:
    num = f"{number:0{width}d}"
    base = f"{num} {rest}" if rest else num
    return base + ext

# ------------------------------------------------------------
# Dateityp-Filter (für files)
# ------------------------------------------------------------


def parse_ext_filter(ext_arg: Optional[str]) -> Optional[Tuple[str, ...]]:
    if not ext_arg:
        return None
    parts = [e.strip() for e in ext_arg.split(",") if e.strip()]
    norm: List[str] = []
    for p in parts:
        if p == "…":
            continue
        if not p.startswith("."):
            p = "." + p
        norm.append(p.lower())
    return tuple(norm) if norm else None


def ext_matches(filename: str, flt: Optional[Tuple[str, ...]]) -> bool:
    if not flt:
        return True
    return os.path.splitext(filename)[1].lower() in flt

# ------------------------------------------------------------
# Scandir-Helfer (sichtbare, nicht-verlinkte Einträge)
# ------------------------------------------------------------


def iter_visible_dirs(path: str) -> Iterable[os.DirEntry]:
    with os.scandir(path) as it:
        dirs = [e for e in it
                if e.is_dir(follow_symlinks=False)
                and not e.is_symlink()
                and e.name != LOCK_DIR_NAME
                and not is_hidden_or_system(e.path)]
    dirs.sort(key=lambda e: sort_key(e.name))
    return dirs


def iter_visible_files(path: str, flt: Optional[Tuple[str, ...]]) -> Iterable[os.DirEntry]:
    with os.scandir(path) as it:
        files = [e for e in it
                 if e.is_file(follow_symlinks=False)
                 and not e.is_symlink()
                 and ext_matches(e.name, flt)
                 and not is_hidden_or_system(e.path)]
    files.sort(key=lambda e: sort_key(e.name))
    return files

# ------------------------------------------------------------
# Konfliktprüfung
# ------------------------------------------------------------


class ConflictError(Exception):
    pass


def check_conflicts_dir(parent_path: str,
                        planned: Dict[str, str],
                        mode_label: str) -> None:
    """
    planned: Mapping alt_basename -> neu_basename (nur solche, die tatsächlich umbenannt werden)
    Prüft:
      - doppelte Zielnamen unter sich
      - Kollision mit unbeteiligten Einträgen im selben Verzeichnis
      - Windows-Name-Validierung
    """
    if not planned:
        return

    seen = {}
    for old, new in planned.items():
        cf = new.casefold()
        if not is_valid_windows_name(new):
            raise ConflictError(
                f"[{mode_label}] Ungültiger Windows-Name: '{new}' in {relwin(parent_path, parent_path)}")
        if cf in seen:
            raise ConflictError(
                f"[{mode_label}] Ziel-Duplikat im selben Ordner: '{new}' kollidiert mit '{seen[cf]}' in {relwin(parent_path, parent_path)}")
        seen[cf] = new

    existing: Dict[str, str] = {}
    with os.scandir(parent_path) as it:
        for e in it:
            if e.name == LOCK_DIR_NAME:
                continue
            if e.is_symlink():
                continue
            if is_hidden_or_system(e.path):
                continue
            existing[e.name.casefold()] = e.name

    for old, new in planned.items():
        new_cf = new.casefold()
        if new_cf in existing:
            if new_cf != old.casefold():
                raise ConflictError(
                    f"[{mode_label}] Zielname existiert bereits: '{new}' in {relwin(parent_path, parent_path)}")

# ------------------------------------------------------------
# Lock-Verzeichnis
# ------------------------------------------------------------


def acquire_lock(root: str) -> str:
    lock_path = os.path.join(root, LOCK_DIR_NAME)
    try:
        os.mkdir(lock_path)
    except FileExistsError:
        raise RuntimeError(
            f"Sperre aktiv: {relwin(lock_path, root)} existiert bereits – paralleler Lauf?")
    # optional PID schreiben
    try:
        with open(os.path.join(lock_path, "pid.txt"), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    # Lock-Ordner als Hidden markieren (ohne andere Attribute zu verlieren)
    try:
        attrs = get_file_attributes(lock_path)
        if attrs is not None:
            SetFileAttributesW(lock_path, attrs | FILE_ATTRIBUTE_HIDDEN)
        else:
            SetFileAttributesW(lock_path, FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass
    return lock_path


def release_lock(lock_path: str) -> None:
    try:
        try:
            os.remove(os.path.join(lock_path, "pid.txt"))
        except OSError:
            pass
        os.rmdir(lock_path)
    except OSError:
        pass

# ------------------------------------------------------------
# Plan-Strukturen
# ------------------------------------------------------------


class DirPlan:
    __slots__ = ("orig_abs", "parent_abs", "old_base",
                 "rest", "final_base", "tmp_base")

    def __init__(self, orig_abs: str, parent_abs: str, old_base: str,
                 rest: str, final_base: str, tmp_base: str) -> None:
        self.orig_abs = orig_abs
        self.parent_abs = parent_abs
        self.old_base = old_base
        self.rest = rest
        self.final_base = final_base
        self.tmp_base = tmp_base


class FilePlan:
    __slots__ = ("orig_abs", "parent_abs", "old_base",
                 "rest", "ext", "final_base", "tmp_base")

    def __init__(self, orig_abs: str, parent_abs: str, old_base: str,
                 rest: str, ext: str, final_base: str, tmp_base: str) -> None:
        self.orig_abs = orig_abs
        self.parent_abs = parent_abs
        self.old_base = old_base
        self.rest = rest
        self.ext = ext
        self.final_base = final_base
        self.tmp_base = tmp_base

# ------------------------------------------------------------
# Planung – Folders
# ------------------------------------------------------------


def enumerate_dirs_preorder(root: str) -> List[Tuple[str, str]]:
    """
    Liefert (abs_path, base) aller Unterordner in Preorder (ohne root selbst).
    """
    result: List[Tuple[str, str]] = []

    def walk(p: str):
        for e in iter_visible_dirs(p):
            result.append((e.path, e.name))
            walk(e.path)

    walk(root)
    return result


def plan_folders(path: str, start: int, step: int, width: int, recursive: bool) -> Tuple[List[DirPlan], int]:
    checked = 0
    plans: List[DirPlan] = []

    if recursive:
        items = enumerate_dirs_preorder(path)
    else:
        items = [(e.path, e.name) for e in iter_visible_dirs(path)]

    number = start
    for abs_path, base in items:
        checked += 1
        rest, _ = strip_numeric_prefix(base, is_file=False)
        final_base = build_target_name(number, width, rest)
        final_base = nfc(collapse_spaces(final_base))
        number += step

        if final_base == base:
            continue

        if not is_valid_windows_name(final_base):
            raise ConflictError(
                f"[folders] Ungültiger Windows-Name: '{final_base}' in {relwin(os.path.dirname(abs_path), path)}")

        tmp_base = f"{base}.renum_tmp_{uuid.uuid4().hex[:12]}"
        plans.append(DirPlan(
            orig_abs=abs_path,
            parent_abs=os.path.dirname(abs_path),
            old_base=base,
            rest=rest,
            final_base=final_base,
            tmp_base=tmp_base
        ))

    # Konfliktprüfung pro Elternordner
    per_parent: Dict[str, Dict[str, str]] = {}
    for dp in plans:
        per_parent.setdefault(dp.parent_abs, {})[dp.old_base] = dp.final_base

    for parent, mapping in per_parent.items():
        check_conflicts_dir(parent, mapping, "folders")

    return plans, checked

# ------------------------------------------------------------
# Planung – Files
# ------------------------------------------------------------


def plan_files(path: str, start: int, step: int, width: int, ext_filter: Optional[Tuple[str, ...]]) -> Tuple[List[FilePlan], int]:
    checked = 0
    plans: List[FilePlan] = []

    files = [(e.path, e.name) for e in iter_visible_files(path, ext_filter)]
    number = start

    for abs_path, base in files:
        checked += 1
        rest, ext = strip_numeric_prefix(base, is_file=True)
        final_base = build_target_name(number, width, rest, ext=ext)
        final_base = nfc(collapse_spaces(final_base))
        number += step

        if final_base == base:
            continue

        if not is_valid_windows_name(final_base):
            raise ConflictError(
                f"[files] Ungültiger Windows-Name: '{final_base}' in {relwin(os.path.dirname(abs_path), path)}")

        tmp_base = f"{base}.renum_tmp_{uuid.uuid4().hex[:12]}"
        plans.append(FilePlan(
            orig_abs=abs_path,
            parent_abs=os.path.dirname(abs_path),
            old_base=base,
            rest=rest,
            ext=ext,
            final_base=final_base,
            tmp_base=tmp_base
        ))

    mapping = {fp.old_base: fp.final_base for fp in plans}
    check_conflicts_dir(path, mapping, "files")

    return plans, checked

# ------------------------------------------------------------
# Ausgabe Plan/Dry-Run
# ------------------------------------------------------------


def print_plan(prefix: str, root: str,
               dplans: List[DirPlan], fplans: List[FilePlan]) -> None:
    for dp in dplans:
        src = os.path.join(dp.parent_abs, dp.old_base)
        dst = os.path.join(dp.parent_abs, dp.final_base)
        print(f"{prefix}: {relwin(src, root)} -> {relwin(dst, root)}")
    for fp in fplans:
        src = os.path.join(fp.parent_abs, fp.old_base)
        dst = os.path.join(fp.parent_abs, fp.final_base)
        print(f"{prefix}: {relwin(src, root)} -> {relwin(dst, root)}")

# ------------------------------------------------------------
# Staging / Commit / Rollback
# ------------------------------------------------------------


def stage_dirs(root: str, dplans: List[DirPlan], verbose: bool = False) -> None:
    planned_by_abs: Dict[str, str] = {
        dp.orig_abs: dp.tmp_base for dp in dplans}
    staged_abs: set = set()

    def stage_under(parent: str):
        for e in iter_visible_dirs(parent):
            stage_under(e.path)
            orig_abs = e.path
            if orig_abs in planned_by_abs and orig_abs not in staged_abs:
                tmp_base = planned_by_abs[orig_abs]
                src = e.path
                dst = os.path.join(parent, tmp_base)
                if verbose:
                    print(
                        f"[StageA] DIR  {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
                os.replace(src, dst)
                staged_abs.add(orig_abs)

    stage_under(root)


def commit_dirs(root: str, dplans: List[DirPlan], verbose: bool = False) -> None:
    tmp_to_final = {dp.tmp_base: dp.final_base for dp in dplans}

    def commit_under(parent: str):
        with os.scandir(parent) as it:
            entries = [e for e in it
                       if e.is_dir(follow_symlinks=False)
                       and not e.is_symlink()
                       and e.name != LOCK_DIR_NAME]
        for e in entries:
            if e.name in tmp_to_final:
                src = e.path
                dst = os.path.join(parent, tmp_to_final[e.name])
                if verbose:
                    print(
                        f"[CommitB] DIR {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
                os.replace(src, dst)
        with os.scandir(parent) as it2:
            for e in it2:
                if e.is_dir(follow_symlinks=False) and not e.is_symlink() and e.name != LOCK_DIR_NAME:
                    commit_under(e.path)

    commit_under(root)


def rollback_dirs(root: str, dplans: List[DirPlan], verbose: bool = False) -> None:
    if not dplans:
        return
    final_to_tmp = {dp.final_base: dp.tmp_base for dp in dplans}
    tmp_to_old = {dp.tmp_base: dp.old_base for dp in dplans}

    def scan_and_rename(parent: str, mapping: Dict[str, str], label: str):
        with os.scandir(parent) as it:
            entries = [e for e in it
                       if e.is_dir(follow_symlinks=False)
                       and not e.is_symlink()
                       and e.name != LOCK_DIR_NAME]
        for e in entries:
            if e.name in mapping:
                src = e.path
                dst = os.path.join(parent, mapping[e.name])
                if verbose:
                    print(
                        f"[Rollback:{label}] DIR {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
                try:
                    os.replace(src, dst)
                except OSError as ex:
                    print(f"[Rollback:{label}] Fehler: {ex}", file=sys.stderr)
        with os.scandir(parent) as it2:
            for e in it2:
                if e.is_dir(follow_symlinks=False) and not e.is_symlink() and e.name != LOCK_DIR_NAME:
                    scan_and_rename(e.path, mapping, label)

    scan_and_rename(root, final_to_tmp, "final→tmp")
    scan_and_rename(root, tmp_to_old,  "tmp→old")


def stage_files(root: str, fplans: List[FilePlan], verbose: bool = False) -> None:
    for fp in fplans:
        src = fp.orig_abs
        dst = os.path.join(fp.parent_abs, fp.tmp_base)
        if verbose:
            print(
                f"[StageA] FILE {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
        os.replace(src, dst)


def commit_files(root: str, fplans: List[FilePlan], verbose: bool = False) -> None:
    tmp_to_final = {fp.tmp_base: fp.final_base for fp in fplans}
    with os.scandir(root) as it:
        entries = [e for e in it if e.is_file(
            follow_symlinks=False) and not e.is_symlink()]
    for e in entries:
        if e.name in tmp_to_final:
            src = e.path
            dst = os.path.join(root, tmp_to_final[e.name])
            if verbose:
                print(
                    f"[CommitB] FILE {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
            os.replace(src, dst)


def rollback_files(root: str, fplans: List[FilePlan], verbose: bool = False) -> None:
    if not fplans:
        return
    final_to_tmp = {fp.final_base: fp.tmp_base for fp in fplans}
    tmp_to_old = {fp.tmp_base: fp.old_base for fp in fplans}

    with os.scandir(root) as it:
        for e in it:
            if e.is_file(follow_symlinks=False) and not e.is_symlink():
                if e.name in final_to_tmp:
                    src = e.path
                    dst = os.path.join(root, final_to_tmp[e.name])
                    if verbose:
                        print(
                            f"[Rollback:final→tmp] FILE {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
                    try:
                        os.replace(src, dst)
                    except OSError as ex:
                        print(
                            f"[Rollback:final→tmp] Fehler: {ex}", file=sys.stderr)

    with os.scandir(root) as it2:
        for e in it2:
            if e.is_file(follow_symlinks=False) and not e.is_symlink():
                if e.name in tmp_to_old:
                    src = e.path
                    dst = os.path.join(root, tmp_to_old[e.name])
                    if verbose:
                        print(
                            f"[Rollback:tmp→old] FILE {relwin(src, root)} -> {relwin(dst, root)}", file=sys.stderr)
                    try:
                        os.replace(src, dst)
                    except OSError as ex:
                        print(
                            f"[Rollback:tmp→old] Fehler: {ex}", file=sys.stderr)

# ------------------------------------------------------------
# Hauptlogik pro Subkommando
# ------------------------------------------------------------


def run_folders(path: str, start: int, step: int, width: int,
                recursive: bool, dry_run: bool, go: bool, verbose: bool) -> int:
    lock = acquire_lock(path)
    try:
        dplans, checked = plan_folders(path, start, step, width, recursive)
        if dry_run or not go:
            print_plan("DRY-RUN", path, dplans, [])
            print(f"Zusammenfassung: geprüft {checked}, geplant {len(dplans)}")
            return 0

        print_plan("PLAN", path, dplans, [])
        try:
            stage_dirs(path, dplans, verbose=verbose)
            commit_dirs(path, dplans, verbose=verbose)
        except Exception as ex:
            print(f"[ERROR] {ex}. Rolle zurück …", file=sys.stderr)
            rollback_dirs(path, dplans, verbose=verbose)
            return 1

        print(f"Fertig: geändert {len(dplans)} (geprüft {checked})")
        return 0
    finally:
        release_lock(lock)


def run_files(path: str, start: int, step: int, width: int, ext_arg: Optional[str],
              dry_run: bool, go: bool, verbose: bool) -> int:
    lock = acquire_lock(path)
    try:
        ext_filter = parse_ext_filter(ext_arg)
        fplans, checked = plan_files(path, start, step, width, ext_filter)
        if dry_run or not go:
            print_plan("DRY-RUN", path, [], fplans)
            print(f"Zusammenfassung: geprüft {checked}, geplant {len(fplans)}")
            return 0

        print_plan("PLAN", path, [], fplans)
        try:
            stage_files(path, fplans, verbose=verbose)
            commit_files(path, fplans, verbose=verbose)
        except Exception as ex:
            print(f"[ERROR] {ex}. Rolle zurück …", file=sys.stderr)
            rollback_files(path, fplans, verbose=verbose)
            return 1

        print(f"Fertig: geändert {len(fplans)} (geprüft {checked})")
        return 0
    finally:
        release_lock(lock)

# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="renum",
        description="Renummeriert Ordner oder Dateien nach Windows-Schema. Ausschließlich für Windows."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    default_start = 0
    default_step = 10
    default_width = 3

    pf = sub.add_parser(
        "folders", help="Ordner umbenennen (optional rekursiv, globale Sequenz)")
    pf.add_argument("path", nargs="?", default=".",
                    help="Zielverzeichnis (Standard: .)")
    pf.add_argument("--start", type=int, default=default_start,
                    help="Startwert (Default: 0)")
    pf.add_argument("--step",  type=int, default=default_step,
                    help="Schrittweite (Default: 10)")
    pf.add_argument("--width", type=int, default=default_width,
                    help="Stellenanzahl / Zero-Pad (Default: 3)")
    pf.add_argument("--dry-run", action="store_true",
                    help="Nur anzeigen, nichts ändern")
    pf.add_argument("--go", action="store_true", help="Tatsächlich umbenennen")
    pf.add_argument("--verbose", action="store_true",
                    help="Ausführliche Logausgaben")
    pf.add_argument("--recursive", action="store_true",
                    help="Rekursiv (globale Sequenz, Preorder)")

    pfi = sub.add_parser("files", help="Dateien umbenennen (nie rekursiv)")
    pfi.add_argument("path", nargs="?", default=".",
                     help="Zielverzeichnis (Standard: .)")
    pfi.add_argument("--start", type=int, default=default_start,
                     help="Startwert (Default: 0)")
    pfi.add_argument("--step",  type=int, default=default_step,
                     help="Schrittweite (Default: 10)")
    pfi.add_argument("--width", type=int, default=default_width,
                     help="Stellenanzahl / Zero-Pad (Default: 3)")
    pfi.add_argument("--dry-run", action="store_true",
                     help="Nur anzeigen, nichts ändern")
    pfi.add_argument("--go", action="store_true",
                     help="Tatsächlich umbenennen")
    pfi.add_argument("--verbose", action="store_true",
                     help="Ausführliche Logausgaben")
    pfi.add_argument("--ext", type=str, default=None,
                     help='Optionale Komma-Liste von Endungen, z.B. ".jpg,.png"')

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    path = os.path.abspath(args.path)

    if os.path.islink(path):
        print("Root-Pfad darf kein Link/Junction sein.", file=sys.stderr)
        return 1

    try:
        if args.cmd == "folders":
            return run_folders(
                path=path,
                start=args.start,
                step=args.step,
                width=args.width,
                recursive=bool(args.recursive),
                dry_run=bool(args.dry_run),
                go=bool(args.go),
                verbose=bool(args.verbose),
            )
        elif args.cmd == "files":
            if getattr(args, "recursive", False):
                print(
                    "Der Modus 'files' unterstützt keinen rekursiven Lauf.", file=sys.stderr)
                return 1
            return run_files(
                path=path,
                start=args.start,
                step=args.step,
                width=args.width,
                ext_arg=args.ext,
                dry_run=bool(args.dry_run),
                go=bool(args.go),
                verbose=bool(args.verbose),
            )
        else:
            parser.print_help()
            return 2
    except ConflictError as ce:
        print(f"Konflikt: {ce}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
