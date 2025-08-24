#!/usr/bin/env python3
"""
renum — Transaktionales Durchnummerieren von Ordnern **oder** Dateien

Subkommandos:
  - renum folders [PATH] [OPTIONS]
  - renum files   [PATH] [OPTIONS]

Eigenschaften
- Nie rekursiv: arbeitet nur im angegebenen Verzeichnis
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
from dataclasses import dataclass
from typing import List, Tuple, Dict, Iterable, Optional
from uuid import uuid4

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
# Scannen & Planung
# -----------------------------


def collect_entries(path: str, include_hidden: bool, pattern: Optional[str], kind: str) -> List[Entry]:
    """kind: 'folders' oder 'files'"""
    entries: List[Entry] = []
    with os.scandir(path) as it:
        for de in it:
            if not include_hidden and is_hidden(de):
                continue
            if pattern and not fnmatch.fnmatch(de.name, pattern):
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
                rest_name = strip_prefix_file(de.name)  # enthält ext
                entries.append(Entry(de.name, os.path.join(
                    path, de.name), rest_name, False))
            else:
                raise ValueError('unbekannter kind-Typ')
    # Windows-„dir“-ähnliche Sortierung nach Originalnamen
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

# -----------------------------
# Locks & Transaktion
# -----------------------------


def preflight_check_locks(plan: List[PlanItem], verbose: bool) -> Tuple[bool, str]:
    for p in plan:
        tmp = p.src_path + f".__probe__{uuid4().hex}"
        try:
            os.rename(p.src_path, tmp)
            os.rename(tmp, p.src_path)
            if verbose:
                print(f"CHECK: {p.src_name} -> frei")
        except Exception as e:
            return False, f"Gesperrt/keine Rechte: {p.src_name} ({e})"
    return True, ''


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


def transactional_execute(plan: List[PlanItem], verbose: bool) -> None:
    to_change = [p for p in plan if not p.unchanged]
    if not to_change:
        if verbose:
            print('Nichts zu ändern – Zielzustand bereits erreicht.')
        return

    temps: Dict[str, Tuple[str, PlanItem]] = {}
    try:
        # Phase A: in eindeutige Temp-Namen verschieben
        for p in to_change:
            tmp_path = p.src_path + f".__renum_tmp__{uuid4().hex}"
            if verbose:
                print(f"A: {p.src_name} -> {os.path.basename(tmp_path)}")
            os.rename(p.src_path, tmp_path)
            temps[p.src_path] = (tmp_path, p)
    except Exception as e:
        print(f"Fehler in Phase A: {e}", file=sys.stderr)
        # Rollback A
        for src, (tmp, item) in list(temps.items())[::-1]:
            try:
                if verbose:
                    print(
                        f"Rollback A: {os.path.basename(tmp)} -> {item.src_name}")
                os.rename(tmp, src)
            except Exception as e2:
                print(
                    f"Rollback A FEHLGESCHLAGEN für {item.src_name}: {e2}", file=sys.stderr)
        raise

    moved_final: List[Tuple[str, PlanItem]] = []
    try:
        # Phase B: von Temp auf finale Namen
        for src, (tmp, item) in temps.items():
            if os.path.exists(item.dst_path):
                raise FileExistsError(
                    f"Ziel existiert unerwartet: {item.dst_name}")
            if verbose:
                print(f"B: {os.path.basename(tmp)} -> {item.dst_name}")
            os.rename(tmp, item.dst_path)
            moved_final.append((item.dst_path, item))
    except Exception as e:
        print(f"Fehler in Phase B: {e}", file=sys.stderr)
        # Rollback B
        for dst, item in list(moved_final)[::-1]:
            try:
                back_tmp = item.src_path + f".__renum_tmp__{uuid4().hex}"
                if verbose:
                    print(
                        f"Rollback B1: {item.dst_name} -> {os.path.basename(back_tmp)}")
                os.rename(dst, back_tmp)
                temps[item.src_path] = (back_tmp, item)
            except Exception as e2:
                print(
                    f"Rollback B1 FEHLGESCHLAGEN für {item.dst_name}: {e2}", file=sys.stderr)
        for src, (tmp, item) in list(temps.items())[::-1]:
            try:
                if verbose:
                    print(
                        f"Rollback B2: {os.path.basename(tmp)} -> {item.src_name}")
                os.rename(tmp, src)
            except Exception as e3:
                print(
                    f"Rollback B2 FEHLGESCHLAGEN für {item.src_name}: {e3}", file=sys.stderr)
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
    p.add_argument('--check-locks', action='store_true',
                   help='Vorab Probe-Umbenennungen (langsamer)')
    p.add_argument('--include-hidden', action='store_true',
                   help='Auch versteckte Einträge einbeziehen')
    p.add_argument(
        '--pattern', help='Nur Namen passend zum GLOB-Muster (z. B. "*Projekt*")')
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
        print(f'Pfad: {base}')

    try:
        entries = collect_entries(
            base, args.include_hidden, args.pattern, kind='folders')
    except FileNotFoundError:
        print(f"Fehler: Pfad nicht gefunden: {base}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Fehler: Keine Berechtigung für Pfad: {base}", file=sys.stderr)
        return 1

    if not entries:
        print('Keine passenden Ordner gefunden.')
        return 0

    try:
        plan = plan_items(entries, args.start, args.step,
                          args.width, kind='folders')
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
        print(
            f"---\n{len(plan)} Ordner geprüft, Änderungen geplant: {sum(1 for p in plan if not p.unchanged)}. Konflikte: 0")
        return 0

    if args.check_locks:
        ok, reason = preflight_check_locks(plan, args.verbose)
        if not ok:
            print(f'Abbruch (Lock/Permission): {reason}', file=sys.stderr)
            return 1

    lock_dir = os.path.join(base, '.renum.lock')
    if not acquire_lock(lock_dir):
        print(
            "Ein anderer 'renum'-Prozess läuft bereits (Lock vorhanden).", file=sys.stderr)
        return 1

    try:
        transactional_execute(plan, args.verbose)
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
        print(f'Pfad: {base}')

    ext_filter: Optional[Iterable[str]] = None
    if args.ext:
        # normalisiere zu set('.jpg', '.png') in lower
        parts = [e.strip().lower() for e in args.ext.split(',') if e.strip()]
        ext_filter = set(e if e.startswith('.') else ('.' + e) for e in parts)

    try:
        entries_all = collect_entries(
            base, args.include_hidden, args.pattern, kind='files')
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
        print(
            f"---\n{len(plan)} Dateien geprüft, Änderungen geplant: {sum(1 for p in plan if not p.unchanged)}. Konflikte: 0")
        return 0

    if args.check_locks:
        ok, reason = preflight_check_locks(plan, args.verbose)
        if not ok:
            print(f'Abbruch (Lock/Permission): {reason}', file=sys.stderr)
            return 1

    lock_dir = os.path.join(base, '.renum.lock')
    if not acquire_lock(lock_dir):
        print(
            "Ein anderer 'renum'-Prozess läuft bereits (Lock vorhanden).", file=sys.stderr)
        return 1

    try:
        transactional_execute(plan, args.verbose)
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
