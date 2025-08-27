#!/usr/bin/env python3
"""
renum — Transaktionales Durchnummerieren von Ordnern **oder** Dateien

Subkommandos:
  - renum folders [PATH] [OPTIONS]
  - renum files   [PATH] [OPTIONS]

Neu (optional):
- `--recursive` nur für `folders`: rekursive Nummerierung in **Preorder (Depth-First)** über den gesamten Baum, mit durchgehender Sequenz. Standard bleibt nicht rekursiv.

Eigenschaften
- Nie rekursiv: arbeitet nur im angegebenen Verzeichnis (optional rekursiv **nur** für `folders` via `--recursive`)
- Sortierung der Originalreihenfolge: Windows-„dir“-ähnlich (case-insensitiv, locale-basiert), ohne `dir` aufzurufen
- Zielschema: "<ZAHL> FOO" (Ordner) bzw. "<ZAHL> FOO.ext" (Dateien)
- Präfixentfernung: vorhandene führende Nummern plus Trennzeichen werden ersetzt
- Nummerierung: --start (0), --step (10), --width (3)
- Modi: --dry-run (Plan), --go (ausführen). Ohne beides → Hilfe.
- Transaktional: zwei Phasen mit vollständigem Rollback (alles-oder-nichts)
- Windows-kompatible Namensvalidierung

Python >= 3.8
"""

from __future__ import annotations
import stat

import argparse
import fnmatch
import os
import platform
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Iterable, Optional
from uuid import uuid4
from pathlib import Path

# -----------------------------
# Datenmodelle
# -----------------------------


@dataclass
class Entry:
    name: str   # Basename (ohne Pfad)
    path: str   # Voller Pfad
    rest: str   # Name ohne existierendes Präfix (bei Dateien: ohne Extension)
    is_dir: bool


@dataclass
class PlanItem:
    src_path: str
    src_name: str
    dst_name: str
    dst_path: str
    unchanged: bool
    # relative Tiefe ab PATH (nur relevant für rekursives folders)
    depth: int = 0

# -----------------------------
# Regex & Utilities
# -----------------------------


# Führendes numerisches Präfix inkl. gängiger Trenner (._- oder bis zu 3 Spaces)
PREFIX_RE = re.compile(r"^\s*(\d+)\s*([._-]|\s{1,3})?\s*")
WS_RE = re.compile(r"\s+")

INVALID_WIN_CHARS = set('<>:"/\\|?*')
RESERVED_WIN_BASENAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}


def is_windows() -> bool:
    return platform.system().lower().startswith('win')


def nfc(s: str) -> str:
    return unicodedata.normalize('NFC', s)


def collapse_spaces(s: str) -> str:
    return WS_RE.sub(' ', s).strip()


def strip_numeric_prefix(text: str) -> str:
    m = PREFIX_RE.match(text)
    rest = text[m.end():] if m else text
    return collapse_spaces(nfc(rest))


def strip_prefix_folder(name: str) -> str:
    # Kompletten Ordnernamen behandeln
    return strip_numeric_prefix(name)


def strip_prefix_file(name: str) -> str:
    # Nur den Stammnamen nummerisch bereinigen, Extension beibehalten
    stem, ext = os.path.splitext(name)
    stem_clean = strip_numeric_prefix(stem)
    return stem_clean + ext


def windows_dir_sort_key(s: str):
    # Case-insensitive, locale-basiert (wie dir)
    import locale
    try:
        locale.setlocale(locale.LC_COLLATE, '')
    except Exception:
        pass
    return locale.strxfrm(s.lower())


def is_hidden(entry) -> bool:
    """Erkennt versteckte Einträge:
    - Unix: führender Punkt
    - Windows: FILE_ATTRIBUTE_HIDDEN oder FILE_ATTRIBUTE_SYSTEM
    """
    try:
        if entry.name.startswith('.'):
            return True
        if is_windows():
            try:
                attrs = entry.stat(follow_symlinks=False).st_file_attributes
                return bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN) or bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
            except Exception:
                return False
        return False
    except Exception:
        return False

# -----------------------------
# Validierung Zielnamen
# -----------------------------


def valid_dir_name(name: str) -> Tuple[bool, str]:
    if not name:
        return False, 'leer'
    if '\x00' in name:
        return False, 'enthält NUL'
    if is_windows():
        if any(ch in INVALID_WIN_CHARS for ch in name):
            return False, 'ungültige Zeichen (Windows)'
        if name.endswith(' ') or name.endswith('.'):
            return False, 'endet mit Leerzeichen/Punkt (Windows)'
        base = name.split('.')[0].upper()
        if base in RESERVED_WIN_BASENAMES:
            return False, 'reservierter Name (Windows)'
    return True, ''


def valid_file_name(name: str) -> Tuple[bool, str]:
    if not name:
        return False, 'leer'
    if '\x00' in name:
        return False, 'enthält NUL'
    if is_windows():
        if any(ch in INVALID_WIN_CHARS for ch in name):
            return False, 'ungültige Zeichen (Windows)'
        if name.endswith(' ') or name.endswith('.'):
            return False, 'endet mit Leerzeichen/Punkt (Windows)'
        stem, _ = os.path.splitext(name)
        if stem.upper() in RESERVED_WIN_BASENAMES:
            return False, 'reservierter Name (Windows)'
    return True, ''

# -----------------------------
# Scannen & Planung (flat)
# -----------------------------


def collect_entries(path: str, include_hidden: bool, pattern: Optional[str], kind: str) -> List[Entry]:
    """Nicht-rekursives Sammeln am Pfad."""
    entries: List[Entry] = []
    with os.scandir(path) as it:
        for de in it:
            if not include_hidden and is_hidden(de):
                continue
            if pattern and not fnmatch.fnmatch(de.name, pattern):
                # Für files/folders flat gilt: pattern filtert die Auswahl vollständig
                continue
            if kind == 'folders':
                if not de.is_dir(follow_symlinks=False):
                    continue
                rest_name = strip_prefix_folder(de.name)
                entries.append(Entry(de.name, os.path.join(
                    path, de.name), rest_name, True))
            elif kind == 'files':
                if not de.is_file(follow_symlinks=False):
                    continue
                rest_name = strip_prefix_file(de.name)
                entries.append(Entry(de.name, os.path.join(
                    path, de.name), rest_name, False))
            else:
                raise ValueError('unbekannter kind-Typ')
    entries.sort(key=lambda e: windows_dir_sort_key(e.name))
    return entries


def plan_items(entries: List[Entry], start: int, step: int, width: int, kind: str) -> List[PlanItem]:
    plan: List[PlanItem] = []
    for i, e in enumerate(entries):
        number = start + i * step
        num = str(number).zfill(width)
        if kind == 'folders':
            rest = strip_prefix_folder(e.name)
            dst_name = f"{num} {rest}" if rest else num
            ok, reason = valid_dir_name(dst_name)
        else:
            stem, ext = os.path.splitext(e.name)
            stem_clean = strip_numeric_prefix(stem)
            dst_name = (f"{num} {stem_clean}" if stem_clean else num) + ext
            ok, reason = valid_file_name(dst_name)
        if not ok:
            raise ValueError(
                f"Ungültiger Zielname für '{e.name}': '{dst_name}' ({reason})")
        dst_name = nfc(dst_name)
        dst_path = os.path.join(os.path.dirname(e.path), dst_name)
        plan.append(PlanItem(e.path, e.name, dst_name,
                    dst_path, e.path == dst_path))

    # Doppelte Zielnamen im Plan verhindern
    seen: Dict[str, str] = {}
    for p in plan:
        if p.dst_name in seen:
            raise ValueError(
                "Konflikt: Mehrere Einträge würden denselben Zielnamen erhalten:\n"
                f"  - {seen[p.dst_name]}\n  - {p.src_name}"
            )
        seen[p.dst_name] = p.src_name
    return plan


def precheck_existing(path: str, plan: List[PlanItem]) -> List[str]:
    existing = set()
    with os.scandir(path) as it:
        for de in it:
            existing.add(de.name)
    planned_src = {os.path.basename(p.src_path) for p in plan}
    conflicts = [
        p.dst_name for p in plan if p.dst_name in existing and p.dst_name not in planned_src]
    return conflicts


def precheck_existing_recursive(plan: List[PlanItem]) -> List[Tuple[str, str]]:
    """Konflikte pro Verzeichnis vorab prüfen.
    Gibt Liste von (directory_path, conflicting_name).
    """
    conflicts: List[Tuple[str, str]] = []
    # gruppiere plan items nach Zielverzeichnis des jeweiligen Items (basierend auf Originalpfaden der Eltern)
    by_dir: Dict[str, List[PlanItem]] = {}
    for p in plan:
        dirpath = os.path.dirname(p.src_path)
        by_dir.setdefault(dirpath, []).append(p)
    for dirpath, items in by_dir.items():
        try:
            existing = set()
            with os.scandir(dirpath) as it:
                for de in it:
                    existing.add(de.name)
        except Exception:
            continue
        planned_src = {os.path.basename(p.src_path) for p in items}
        for p in items:
            if p.dst_name in existing and p.dst_name not in planned_src:
                conflicts.append((dirpath, p.dst_name))
    return conflicts

# -----------------------------
# Rekursives Sammeln & Planung für folders
# -----------------------------


def iter_dir_sorted(path: str, include_hidden: bool) -> List[os.DirEntry]:
    entries = []
    with os.scandir(path) as it:
        for de in it:
            if not include_hidden and is_hidden(de):
                continue
            if not de.is_dir(follow_symlinks=False):
                continue
            entries.append(de)
    entries.sort(key=lambda d: windows_dir_sort_key(d.name))
    return entries


def collect_folders_recursive(root: str, include_hidden: bool) -> List[Tuple[str, str, int]]:
    """Gibt eine Liste (path, name, depth) in Preorder zurück (Eltern vor Kindern)."""
    out: List[Tuple[str, str, int]] = []

    def _walk(cur: str, depth: int):
        # Füge aktuelle Ebene (nur Unterordner von cur) sortiert hinzu
        for de in iter_dir_sorted(cur, include_hidden):
            out.append((de.path, de.name, depth))
            # tiefer gehen
            _walk(de.path, depth + 1)
    _walk(root, 0)
    return out


def plan_folders_recursive(root: str, include_hidden: bool, pattern: Optional[str], start: int, step: int, width: int) -> List[PlanItem]:
    preorder = collect_folders_recursive(root, include_hidden)
    plan: List[PlanItem] = []
    counter = 0
    for full_path, name, depth in preorder:
        # Nur umbenennen, wenn pattern None oder matcht; traversiert wird immer
        will_rename = (pattern is None) or fnmatch.fnmatch(name, pattern)
        if will_rename:
            num = str(start + counter * step).zfill(width)
            rest = strip_prefix_folder(name)
            dst_name = f"{num} {rest}" if rest else num
            dst_name = nfc(dst_name)
            ok, reason = valid_dir_name(dst_name)
            if not ok:
                raise ValueError(
                    f"Ungültiger Zielname für '{name}': '{dst_name}' ({reason})")
        else:
            dst_name = name  # unverändert
        plan.append(PlanItem(src_path=full_path, src_name=name, dst_name=dst_name,
                    dst_path='', unchanged=(dst_name == name), depth=depth))
        counter += 1  # globale Sequenz, auch wenn Ordner selbst nicht umbenannt wird

    # Nun Zielpfade berechnen: für jeden Knoten Pfad mit ggf. umbenannten Vorfahren
    # Baue ein Mapping alter->PlanItem für schnellen Zugriff
    by_path = {p.src_path: p for p in plan}
    # Sortiere nach Pfadlänge aufsteigend, damit Eltern vor Kindern berechnet werden
    for p in sorted(plan, key=lambda x: (x.depth, len(x.src_path))):
        parent = os.path.dirname(p.src_path)
        if parent == root:
            dst_dir = root
        else:
            # Wir müssen den Zielpfad des Eltern-PlanItems finden
            parent_item = by_path.get(parent)
            dst_dir = parent_item.dst_path if parent_item else parent
        p.dst_path = os.path.join(dst_dir, p.dst_name)
    return plan

# -----------------------------
# Locks & Transaktion
# -----------------------------


def acquire_lock(lock_path: str) -> bool:
    try:
        os.mkdir(lock_path)
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def release_lock(lock_path: str) -> None:
    try:
        os.rmdir(lock_path)
    except Exception:
        pass


def transactional_execute(plan: List[PlanItem], verbose: bool, depth_sensitive: bool = False, base: Optional[str] = None) -> None:
    """Zwei-Phasen-Umbenennung mit vollständigem Rollback.
    - Phase A: in eindeutige Temp-Namen verschieben (rekursiv: leaf -> root)
    - Phase B: Temp auf finale Namen (rekursiv: root -> leaf)
    """
    to_change = [
        p for p in plan if not p.unchanged and p.src_path != p.dst_path]
    if not to_change:
        if verbose:
            print('Nichts zu ändern – Zielzustand bereits erreicht.')
        return

    # Reihenfolge für Phase A
    if depth_sensitive:
        phaseA = sorted(to_change, key=lambda p: p.depth,
                        reverse=True)  # leaf -> root
    else:
        phaseA = to_change

    temps: Dict[str, Tuple[str, PlanItem]] = {}
    try:
        for p in phaseA:
            tmp_path = p.src_path + f".__renum_tmp__{uuid4().hex}"
            src_disp = Path(os.path.relpath(p.src_path, base)).as_posix(
            ) if base else Path(p.src_path).as_posix()
            tmp_disp = Path(os.path.relpath(tmp_path, base)).as_posix(
            ) if base else Path(tmp_path).as_posix()
            if verbose:
                print(f"A: ./{src_disp} -> ./{tmp_disp}")
            os.rename(p.src_path, tmp_path)
            temps[p.src_path] = (tmp_path, p)
    except Exception as e:
        print(f"Fehler in Phase A: {e}", file=sys.stderr)
        # Rollback A (Temp -> Original)
        for src, (tmp, item) in list(temps.items())[::-1]:
            tmp_disp = Path(os.path.relpath(tmp, base)).as_posix(
            ) if base else Path(tmp).as_posix()
            src_disp = Path(os.path.relpath(src, base)).as_posix(
            ) if base else Path(src).as_posix()
            if verbose:
                print(f"Rollback A: ./{tmp_disp} -> ./{src_disp}")
            try:
                os.rename(tmp, src)
            except Exception as e2:
                print(
                    f"Rollback A FEHLGESCHLAGEN für ./{src_disp}: {e2}", file=sys.stderr)
        raise

    # Reihenfolge für Phase B
    items_B = list(temps.items())
    if depth_sensitive:
        # root -> leaf
        items_B = sorted(items_B, key=lambda kv: kv[1][1].depth)

    moved_final: List[Tuple[str, PlanItem]] = []
    try:
        for src, (tmp, item) in items_B:
            dst_disp = Path(os.path.relpath(item.dst_path, base)).as_posix(
            ) if base else Path(item.dst_path).as_posix()
            tmp_disp = Path(os.path.relpath(tmp, base)).as_posix(
            ) if base else Path(tmp).as_posix()
            if os.path.exists(item.dst_path):
                raise FileExistsError(
                    f"Ziel existiert unerwartet: ./{dst_disp}")
            if verbose:
                print(f"B: ./{tmp_disp} -> ./{dst_disp}")
            os.rename(tmp, item.dst_path)
            moved_final.append((item.dst_path, item))
    except Exception as e:
        print(f"Fehler in Phase B: {e}", file=sys.stderr)
        # Rollback B (final -> neue Temp) und dann Temp -> Original
        for dst, item in list(moved_final)[::-1]:
            back_tmp = item.src_path + f".__renum_tmp__{uuid4().hex}"
            dst_disp = Path(os.path.relpath(dst, base)).as_posix(
            ) if base else Path(dst).as_posix()
            back_disp = Path(os.path.relpath(back_tmp, base)).as_posix(
            ) if base else Path(back_tmp).as_posix()
            if verbose:
                print(f"Rollback B1: ./{dst_disp} -> ./{back_disp}")
            try:
                os.rename(dst, back_tmp)
                temps[item.src_path] = (back_tmp, item)
            except Exception as e2:
                print(
                    f"Rollback B1 FEHLGESCHLAGEN für ./{dst_disp}: {e2}", file=sys.stderr)
        for src, (tmp, item) in list(temps.items())[::-1]:
            tmp_disp = Path(os.path.relpath(tmp, base)).as_posix(
            ) if base else Path(tmp).as_posix()
            src_disp = Path(os.path.relpath(src, base)).as_posix(
            ) if base else Path(src).as_posix()
            if verbose:
                print(f"Rollback B2: ./{tmp_disp} -> ./{src_disp}")
            try:
                os.rename(tmp, src)
            except Exception as e3:
                print(
                    f"Rollback B2 FEHLGESCHLAGEN für ./{src_disp}: {e3}", file=sys.stderr)
        raise

# -----------------------------
# CLI: Parser & Subkommandos
# -----------------------------


def add_common_options(p: argparse.ArgumentParser) -> None:
    p.add_argument('path', nargs='?', default='.', help='Zielverzeichnis')
    p.add_argument('--start', type=int, default=0, help='Erste Zahl')
    p.add_argument('--step', type=int, default=10, help='Abstand der Nummern')
    p.add_argument('--width', type=int, default=3,
                   help='Stellenanzahl (Zero-Pad)')
    p.add_argument('--dry-run', action='store_true',
                   help='Nur anzeigen, keine Änderungen')
    p.add_argument('--go', action='store_true',
                   help='Änderungen wirklich durchführen')
    p.add_argument('--verbose', action='store_true',
                   help='Ausführliche Ausgabe')


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog='renum',
        description="Durchnummerieren von Ordnern oder Dateien (transaktional)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = ap.add_subparsers(dest='command', metavar='command')

    p_folders = sub.add_parser('folders', help='Ordner umbenennen')
    add_common_options(p_folders)
    p_folders.add_argument('--recursive', action='store_true',
                           help='Rekursiv über Unterordner (Preorder, globale Sequenz)')

    p_files = sub.add_parser('files', help='Dateien umbenennen')
    add_common_options(p_files)
    p_files.add_argument(
        '--ext', help='Nur diese Extensions (Kommaliste, z. B. ".jpg,.png")')

    return ap

# -----------------------------
# Ausführung pro Subkommando
# -----------------------------


def run_folders(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.go:
        build_parser().parse_args(['folders', '--help'])
        return 0

    base = os.path.abspath(args.path)
    if args.verbose:
        cwd = os.getcwd()
        base_disp = Path(os.path.relpath(base, cwd)).as_posix()
        print(f'Pfad: ./{base_disp}')

    try:
        if args.recursive:
            plan = plan_folders_recursive(
                base, include_hidden=False, pattern=None, start=args.start, step=args.step, width=args.width)
        else:
            entries = collect_entries(
                base, include_hidden=False, pattern=None, kind='folders')
            if not entries:
                print('Keine passenden Ordner gefunden.')
                return 0
            plan = plan_items(entries, args.start, args.step,
                              args.width, kind='folders')
    except (FileNotFoundError, PermissionError) as e:
        print(f"Fehler beim Scannen: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f'Fehler in Planung: {e}', file=sys.stderr)
        return 1

    # Konflikte prüfen
    if args.recursive:
        conflicts_pairs = precheck_existing_recursive(plan)
        if conflicts_pairs:
            print('Konflikt(e) gefunden (vorhandene Einträge blockieren Zielnamen):')
            for dirpath, name in conflicts_pairs:
                rel = Path(os.path.relpath(dirpath, base)).as_posix()
                print(f'  [./{rel}] {name}')
            print('Abbruch ohne Änderungen.', file=sys.stderr)
            return 1
    else:
        conflicts = precheck_existing(base, plan)
        if conflicts:
            print('Konflikt: Folgende Zielnamen existieren bereits:')
            for n in conflicts:
                print(f'  - {n}')
            print('Abbruch ohne Änderungen.', file=sys.stderr)
            return 1

    # Ausgabe
    if args.recursive and args.dry_run:
        # Flache Darstellung mit POSIX-relativen Pfaden (plattformneutral)
        for p in plan:
            rel_src = Path(os.path.relpath(p.src_path, base)).as_posix()
            rel_dst = Path(os.path.relpath(p.dst_path, base)).as_posix()
            print(f"DRY-RUN: ./{rel_src} -> ./{rel_dst}")
        total = len(plan)
        changed = sum(1 for p in plan if (not p.unchanged)
                      or (p.src_path != p.dst_path))
        print(
            f"---{total} Ordner geprüft, Änderungen geplant: {changed}. Konflikte: 0")
        return 0
    else:
        for item in plan:
            prefix = 'DRY-RUN:' if args.dry_run else 'PLAN:'
            print(f"{prefix} ./{item.src_name:<30} -> ./{item.dst_name}")

    if args.dry_run:
        total = len(plan)
        changed = sum(1 for p in plan if not p.unchanged)
        print(
            f"---{total} Ordner geprüft, Änderungen geplant: {changed}. Konflikte: 0")
        return 0

    lock_dir = os.path.join(base, '.renum.lock')
    if not acquire_lock(lock_dir):
        print(
            "Ein anderer 'renum'-Prozess läuft bereits (Lock vorhanden).", file=sys.stderr)
        return 1

    try:
        transactional_execute(plan, args.verbose,
                              depth_sensitive=args.recursive, base=base)
    except Exception:
        print('Änderungen vollständig zurückgerollt (Fehler).', file=sys.stderr)
        release_lock(lock_dir)
        return 1

    release_lock(lock_dir)
    print('Fertig. Alle Umbenennungen erfolgreich durchgeführt.')
    return 0


def run_files(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.go:
        build_parser().parse_args(['files', '--help'])
        return 0

    base = os.path.abspath(args.path)
    if args.verbose:
        cwd = os.getcwd()
        base_disp = Path(os.path.relpath(base, cwd)).as_posix()
        print(f'Pfad: ./{base_disp}')

    ext_filter: Optional[Iterable[str]] = None
    if args.ext:
        # normalisiere zu set('.jpg', '.png') in lower
        parts = [e.strip().lower() for e in args.ext.split(',') if e.strip()]
        ext_filter = set(e if e.startswith('.') else ('.' + e) for e in parts)

    try:
        entries_all = collect_entries(
            base, include_hidden=False, pattern=None, kind='files')
    except FileNotFoundError:
        print(f"Fehler: Pfad nicht gefunden: {base}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Fehler: Keine Berechtigung für Pfad: {base}", file=sys.stderr)
        return 1

    if ext_filter is not None:
        entries = []
        for e in entries_all:
            _, ext = os.path.splitext(e.name)
            if ext.lower() in ext_filter:
                entries.append(e)
    else:
        entries = entries_all

    if not entries:
        print('Keine passenden Dateien gefunden.')
        return 0

    try:
        plan = plan_items(entries, args.start, args.step,
                          args.width, kind='files')
    except ValueError as e:
        print(f'Fehler in Planung: {e}', file=sys.stderr)
        return 1

    conflicts = precheck_existing(base, plan)
    if conflicts:
        print('Konflikt: Folgende Zielnamen existieren bereits:')
        for n in conflicts:
            print(f'  - {n}')
        print('Abbruch ohne Änderungen.', file=sys.stderr)
        return 1

    for item in plan:
        prefix = 'DRY-RUN:' if args.dry_run else 'PLAN:'
        print(f"{prefix} ./{item.src_name:<30} -> ./{item.dst_name}")

    if args.dry_run:
        total = len(plan)
        changed = sum(1 for p in plan if not p.unchanged)
        print(
            f"---{total} Dateien geprüft, Änderungen geplant: {changed}. Konflikte: 0")
        return 0

    lock_dir = os.path.join(base, '.renum.lock')
    if not acquire_lock(lock_dir):
        print(
            "Ein anderer 'renum'-Prozess läuft bereits (Lock vorhanden).", file=sys.stderr)
        return 1

    try:
        transactional_execute(plan, args.verbose, base=base)
    except Exception:
        print('Änderungen vollständig zurückgerollt (Fehler).', file=sys.stderr)
        release_lock(lock_dir)
        return 1

    release_lock(lock_dir)
    print('Fertig. Alle Umbenennungen erfolgreich durchgeführt.')
    return 0

# -----------------------------
# Main
# -----------------------------


def main(argv: List[str]) -> int:
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)

    if args.command == 'folders':
        return run_folders(args)
    elif args.command == 'files':
        return run_files(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
