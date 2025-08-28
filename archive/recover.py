#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recover.py — Konsistenz-Audit für pics/icons/Ordnerstruktur

Modi:
  (ohne Option)   -> Audit/Konsistenzprüfung (read-only)
  --renum-pics    -> (Stub) PNGs auf 10er-Raster umnummerieren
  --build-icons   -> (Stub) ICOs frisch aus pics bauen
  --rebuild-folders -> (Stub) Ordner & desktop.ini nachziehen

Globale Flags:
  --dry-run       -> keine Schreibaktionen (Audit ist ohnehin read-only)
  -v / -vv        -> ausführlichere Logs
  --no-color      -> Farboutput deaktivieren

Exitcodes:
  0 = OK
  1 = nur Warnungen
  2 = Fehler
"""

from __future__ import annotations
import stat
from uuid import uuid4
from pathlib import PureWindowsPath, Path
import argparse
import json
import os
import re
import sys
import uuid
import subprocess
import shutil
from datetime import datetime
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- Konstante Vorgaben laut Spez ----------
PICS_DIR = Path("pics")
ICONS_DIR = Path("icons")
DESKTOP_INI = "desktop.ini"

# desktop.ini-Soll (Inhalt exakt kontrollieren wir mindestens für IconResource,
# die restlichen Felder werden auf Existenz geprüft).
INI_SECTION_SHELL = "[.ShellClassInfo]"
INI_SECTION_VIEW = "[ViewState]"
INI_FOLDER_TYPE_LINE = "FolderType=Music"

# Regex für "NNN NAME"
ID_RE = re.compile(r"^(?P<num>\d{3})\s+(?P<name>.+)$")

# Windows-verbotene Zeichen in Namen (Datei- und Ordnernamen)
WIN_FORBIDDEN_CHARS = set('<>:"/\\|?*')
WIN_RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# ---------- CLI / Globale Flags ----------


class Cfg:
    verbose: int = 0
    dry_run: bool = False
    use_color: bool = True


cfg = Cfg()

# ---------- Utility: Ausgabe ----------


def supports_color() -> bool:
    if cfg.use_color is False:
        return False
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def c(text: str, col: str) -> str:
    if not supports_color():
        return text
    colors = {
        "gray": "\033[90m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "reset": "\033[0m",
    }
    return f"{colors.get(col, '')}{text}{colors['reset']}"


def log(msg: str, level: str = "INFO", detail: int = 0):
    if detail > cfg.verbose:
        return
    tag = {
        "DEBUG": c("DEBUG", "blue"),
        "INFO": c("INFO ", "green"),
        "WARN": c("WARN ", "yellow"),
        "ERROR": c("ERROR", "red"),
    }[level]
    print(f"{tag} {msg}")

# ---------- Datenstrukturen ----------


@dataclass
class Finding:
    severity: str   # INFO/WARN/ERROR
    code: str       # z.B. E_MISSING_ICON
    subject: str    # betroffener Pfad oder ID
    expected: Optional[str] = None
    actual: Optional[str] = None
    hint: Optional[str] = None

# ---------- Normalisierung / Parsing ----------


def normalize_name(name: str) -> str:
    # Trimmen, Mehrfachspaces komprimieren, casefold für matching
    n = " ".join(name.strip().split())
    return n.casefold()


def parse_id_from_basename(basename: str) -> Optional[Tuple[str, str]]:
    m = ID_RE.match(basename)
    if not m:
        return None
    num = m.group("num")
    name = m.group("name")
    return num, name


def invalid_windows_name(name: str) -> Optional[str]:
    # Prüfe verbotene Zeichen
    if any(ch in WIN_FORBIDDEN_CHARS for ch in name):
        return "forbidden_char"
    # Prüfe reservierte Basenames (ohne Erweiterung)
    base = name
    if "." in base:
        base = base.split(".")[0]
    if base.upper() in WIN_RESERVED_BASENAMES:
        return "reserved"
    # Leading/Trailing Dot/Space sind unter Windows problematisch
    if name.strip() != name or name.endswith(".") or name.startswith("."):
        return "whitespace_or_dot"
    return None

# ---------- Audit-Logik ----------


def audit() -> int:
    findings: List[Finding] = []

    # 0) Grundvoraussetzungen
    if not PICS_DIR.exists() or not PICS_DIR.is_dir():
        log(f"Erwarteter Ordner fehlt: ./{PICS_DIR}", "ERROR")
        findings.append(Finding("ERROR", "E_NO_PICS_DIR",
                        str(PICS_DIR), hint="Lege ./pics an."))
    if not ICONS_DIR.exists() or not ICONS_DIR.is_dir():
        log(f"Erwarteter Ordner fehlt: ./{ICONS_DIR}", "ERROR")
        findings.append(Finding("ERROR", "E_NO_ICONS_DIR",
                        str(ICONS_DIR), hint="Lege ./icons an."))

    # Wenn Grundordner fehlen, brechen wir nach Report ab.
    if any(f.severity == "ERROR" and f.code in {"E_NO_PICS_DIR", "E_NO_ICONS_DIR"} for f in findings):
        return finalize(findings)

    # 1) PNGs einlesen
    png_files = sorted([p for p in PICS_DIR.glob("*.png")] +
                       [p for p in PICS_DIR.glob("*.PNG")])
    png_ids: Dict[str, Path] = {}
    png_nums: Dict[int, List[str]] = defaultdict(list)
    png_names_norm: Dict[str, List[str]] = defaultdict(list)

    # Schemafehler in pics
    for p in sorted(PICS_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() != ".png":
            continue
        if p.is_file() and p.suffix.lower() == ".png":
            base = p.stem
            parsed = parse_id_from_basename(base)
            if not parsed:
                findings.append(Finding("ERROR", "E_SCHEMA_PIC", str(
                    p), hint="Erwartet: 'NNN NAME.png'"))
                log(f"Schemafehler in pics: {p.name}", "ERROR")
                continue
            num, name = parsed
            inv = invalid_windows_name(f"{num} {name}")
            if inv:
                findings.append(Finding("ERROR", "E_INVALID_PIC_NAME", str(
                    p), hint=f"Ungültiger Name ({inv})."))
                log(f"Ungültiger PNG-Name: {p.name}", "ERROR")
                continue
            pic_id = f"{num} {name}"
            if pic_id in png_ids:
                findings.append(Finding("ERROR", "E_DUP_PIC_ID", str(
                    p), actual=pic_id, hint="Doppelter Ident-String in pics."))
                log(f"Doppelter Ident in pics: {pic_id}", "ERROR")
            else:
                png_ids[pic_id] = p
                try:
                    nnum = int(num)
                    png_nums[nnum].append(pic_id)
                except ValueError:
                    pass
                png_names_norm[normalize_name(name)].append(pic_id)

    # 2) ICOs einlesen (für Orphans/Schema)
    ico_all: Dict[str, Path] = {}
    for p in sorted(ICONS_DIR.glob("*.ico")) + sorted(ICONS_DIR.glob("*.ICO")):
        base = p.stem
        parsed = parse_id_from_basename(base)
        if not parsed:
            findings.append(Finding("WARN", "W_SCHEMA_ICON",
                            str(p), hint="Erwartet: 'NNN NAME.ico'"))
            log(f"Schemawarnung in icons: {p.name}", "WARN")
            continue
        num, name = parsed
        inv = invalid_windows_name(f"{num} {name}")
        if inv:
            findings.append(Finding("ERROR", "E_INVALID_ICON_NAME", str(
                p), hint=f"Ungültiger Name ({inv})."))
            log(f"Ungültiger ICO-Name: {p.name}", "ERROR")
            continue
        ico_all[f"{num} {name}"] = p

    # 3) Ordner (für Orphans/INI)
    folders_all: Dict[str, Path] = {}
    for p in sorted(Path(".").iterdir()):
        if not p.is_dir():
            continue
        if p.name in {PICS_DIR.name, ICONS_DIR.name}:
            continue
        parsed = parse_id_from_basename(p.name)
        if not parsed:
            # Ordner außerhalb des Schemas ignorieren
            continue
        num, name = parsed
        inv = invalid_windows_name(p.name)
        if inv:
            findings.append(Finding("ERROR", "E_INVALID_FOLDER_NAME", str(
                p), hint=f"Ungültiger Name ({inv})."))
            log(f"Ungültiger Ordnername: {p}", "ERROR")
            continue
        folders_all[f"{num} {name}"] = p

    # 4) 1:1-Konsistenz je PNG
    for pic_id, pic_path in png_ids.items():
        num, name = pic_id.split(" ", 1)
        # ICO vorhanden?
        ico_path = ICONS_DIR / f"{pic_id}.ico"
        if not ico_path.exists():
            findings.append(Finding("ERROR", "E_MISSING_ICON", pic_id, expected=str(
                ico_path), hint="Icon fehlt zu PNG."))
            log(f"Fehlendes ICO: {ico_path}", "ERROR")
        # Ordner vorhanden?
        folder_path = folders_all.get(pic_id)
        if not folder_path:
            # gibt es evtl. einen Ordner mit gleichem NAME aber falscher Nummer?
            # (nur Info fürs Audit)
            name_matches = [
                k for k in folders_all.keys() if k.endswith(f" {name}")]
            if name_matches:
                findings.append(Finding("WARN", "W_FOLDER_WRONG_INDEX", pic_id, actual=", ".join(
                    name_matches), hint="Ordner vorhanden, aber mit anderer Nummer."))
                log(
                    f"Ordner existiert mit anderer Nummer für NAME '{name}': {name_matches}", "WARN")
            else:
                findings.append(Finding("ERROR", "E_MISSING_FOLDER", pic_id, expected=str(
                    Path(".") / pic_id), hint="Ordner fehlt zu PNG."))
                log(f"Fehlender Ordner: ./{pic_id}/", "ERROR")
        else:
            # desktop.ini prüfen
            ini_file = folder_path / DESKTOP_INI
            if not ini_file.exists():
                findings.append(Finding("ERROR", "E_MISSING_INI", str(
                    folder_path), expected=DESKTOP_INI, hint="desktop.ini fehlt."))
                log(f"desktop.ini fehlt: {folder_path}", "ERROR")
            else:
                ok, exp, act, hint = check_desktop_ini(ini_file, pic_id)
                if not ok:
                    findings.append(Finding("ERROR", "E_BAD_INI", str(
                        ini_file), expected=exp, actual=act, hint=hint))
                    log(f"Falsche desktop.ini in {folder_path}", "ERROR")

    # 5) Orphans: ICO ohne PNG, Ordner ohne PNG
    for ico_id, ico_path in ico_all.items():
        if ico_id not in png_ids:
            findings.append(Finding("WARN", "W_ORPHAN_ICON", ico_id, actual=str(
                ico_path), hint="ICO ohne zugehöriges PNG."))
            log(f"Verwaistes ICO: {ico_path}", "WARN")

    for folder_id, folder_path in folders_all.items():
        if folder_id not in png_ids:
            findings.append(Finding("WARN", "W_ORPHAN_FOLDER", folder_id, actual=str(
                folder_path), hint="Ordner ohne zugehöriges PNG."))
            log(f"Verwaister Ordner: {folder_path}", "WARN")

    # 6) Dubletten & Policy-Hinweise
    # Doppelte Nummern (in pics)
    for num, ids in png_nums.items():
        if len(ids) > 1:
            findings.append(Finding("ERROR", "E_DUP_NUMBER", f"{num:03d}", actual=", ".join(
                ids), hint="Mehrere PNGs mit gleicher Nummer."))
            log(f"Doppelte Nummer {num:03d}: {ids}", "ERROR")

    # Doppelte Namen (normalisiert)
    for nname, ids in png_names_norm.items():
        if len(ids) > 1:
            findings.append(Finding("WARN", "W_DUP_NAME", nname, actual=", ".join(
                ids), hint="Mehrere PNGs mit gleichem NAME (normalisiert)."))
            log(f"Doppelter NAME (norm): {nname} -> {ids}", "WARN")

    # Nummern-Policy: Start 000, Schritt 10, Lücken
    if png_nums:
        sorted_nums = sorted(png_nums.keys())
        if sorted_nums[0] != 0:
            findings.append(Finding("WARN", "W_POLICY_START", "start", expected="000",
                            actual=f"{sorted_nums[0]:03d}", hint="Nummern beginnen nicht bei 000."))
            log(
                f"Nummernraster: Start ist {sorted_nums[0]:03d}, erwartet 000", "WARN")
        # Schrittweite prüfen
        diffs = [b - a for a, b in zip(sorted_nums, sorted_nums[1:])]
        if any(d != 10 for d in diffs):
            findings.append(Finding("WARN", "W_POLICY_STEP", "step", expected="10", actual=",".join(
                map(str, diffs)), hint="Schrittweite ungleich 10 oder uneinheitlich."))
            log(f"Uneinheitliche Schrittweiten: {diffs}", "WARN")
        # Lücken (implizit über Schritt ≠ 10)
        # Optional: explizite Liste fehlender Nummern
        missing = []
        if sorted_nums:
            target = list(range(sorted_nums[0], sorted_nums[-1] + 10, 10))
            missing = sorted(set(target) - set(sorted_nums))
        if missing:
            findings.append(Finding("WARN", "W_POLICY_GAPS", "gaps", actual=", ".join(
                f"{m:03d}" for m in missing), hint="Lücken im 10er-Raster."))
            log(f"Lücken im Raster: {[f'{m:03d}' for m in missing]}", "WARN")

    return finalize(findings)


def check_desktop_ini(ini_path: Path, pic_id: str):
    # Erwarteten Pfad robust konstruieren
    expected_path = str(PureWindowsPath("..") / "icons" / f"{pic_id}.ico")
    # z.B. ..\icons\000 ACCOUSTIC.ico,0
    expected_value = expected_path + ",0"

    try:
        content = ini_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = ini_path.read_text(encoding="cp1252", errors="ignore")

    # letzte IconResource-Zeile nehmen
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    icons = [ln for ln in lines if ln.lower().startswith("iconresource=")]
    if not icons:
        return False, expected_value, "<missing IconResource>", "IconResource fehlt."

    raw = icons[-1].split("=", 1)[1].strip().strip('"').strip("'")
    # Slashes normalisieren und case-insensitiv vergleichen
    actual = raw.replace("/", "\\")
    # (optional) doppelte Backslashes zusammenfassen:
    while "\\\\" in actual:
        actual = actual.replace("\\\\", "\\")

    ok = actual.casefold() == expected_value.casefold()
    return ok, expected_value, raw, ("" if ok else "IconResource verweist nicht auf das erwartete ICO.")


def natural_sort_key_name(name: str) -> tuple:
    # einfache natürliche Sortierung: casefold + split in Ziffern/Non-Ziffern
    import itertools

    def chunks(s):
        buf = ""
        digit = None
        for ch in s:
            if ch.isdigit():
                if digit is False:
                    yield buf
                    buf = ch
                else:
                    buf += ch
                digit = True
            else:
                if digit is True:
                    yield int(buf)
                    buf = ch
                else:
                    buf += ch
                digit = False
        if buf:
            yield int(buf) if digit else buf
    return tuple((str(x).casefold() if not isinstance(x, int) else x) for x in chunks(name))


def ensure_unique_temp_file(target_dir: Path, suffix: str = ".png") -> Path:
    # erzeugt garantiert nicht kollidierenden Temp-Dateinamen im Zielverzeichnis
    while True:
        p = target_dir / f".__renum_tmp__{uuid.uuid4().hex}{suffix}"
        if not p.exists():
            return p


def two_phase_file_renames(mapping: Dict[Path, Path]) -> None:
    """
    Führt eine Menge von Datei-Renames kollisionsfrei aus:
    1) alle Quellen -> eindeutige Tempnamen
    2) alle Temp -> Zielnamen
    """
    if not mapping:
        return
    srcs = list(mapping.keys())
    temps: Dict[Path, Path] = {}
    # Phase 1: in temp
    for src in srcs:
        tmp = ensure_unique_temp_file(src.parent, suffix=src.suffix)
        src.rename(tmp)
        temps[src] = tmp
    # Phase 2: temp -> final
    for src in srcs:
        tmp = temps[src]
        dst = mapping[src]
        tmp.rename(dst)


def find_im_binary() -> list[str]:
    """Bevorzugt IM7 ('magick'), fällt auf IM6 ('convert') zurück."""
    for cand in ("magick", "magick.exe"):
        if shutil.which(cand):
            return [cand]
    for cand in ("convert", "convert.exe"):
        if shutil.which(cand):
            return [cand]
    return []


def ts_token() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def make_tmpdir(base: Path) -> Path:
    d = base / f".recover_tmp-{ts_token()}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def run_im(cmd: list[str]) -> tuple[bool, str]:
    """Führt ein IM-Kommando aus, gibt (ok, stderr_text) zurück."""
    try:
        res = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, res.stderr.decode(errors="ignore")
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode(errors="ignore")[:1200]


def im_norm_command(im_bin: list[str], src: Path, dst: Path, size: int) -> list[str]:
    """
    Normierung pro Frame:
      - cover-Resize (^), zentriert
      - weißer Hintergrund, Alpha entfernt
      - sRGB, 8-Bit, TrueColor, keine Palette, strip
    """
    return (
        im_bin
        + [
            str(src),
            "-colorspace", "sRGB",
            "-resize", f"{size}x{size}^",
            "-gravity", "center",
            "-extent", f"{size}x{size}",
            "-background", "white",
            "-flatten",
            "-depth", "8",
            "-alpha", "off",
            "-type", "TrueColor",
            "-define", "png:color-type=2",
            "-strip",
            str(dst),
        ]
    )


def im_ico_command(im_bin: list[str], inputs: list[Path], out_ico: Path, icon_format: Optional[str]) -> list[str]:
    cmd = im_bin + [str(p) for p in inputs]
    # Vereinheitlichung & optionales Frame-Format
    if icon_format in {"bmp", "png"}:
        cmd += ["-define", f"icon:format={icon_format}"]
    cmd += ["-colorspace", "sRGB", "-depth", "8", "-alpha",
            "off", "-type", "TrueColor", str(out_ico)]
    return cmd


def ensure_unique_temp_dir(parent: Path) -> Path:
    while True:
        p = parent / f".__ren_dir_tmp__{uuid4().hex}"
        if not p.exists():
            return p


def two_phase_dir_renames(mapping: Dict[Path, Path]) -> None:
    """
    Kollisionsfreie Ordner-Umbenennungen:
      1) alle src -> eindeutige Temp-Verzeichnisse
      2) alle temp -> final dst
    """
    if not mapping:
        return
    temps: Dict[Path, Path] = {}
    # Phase 1: src -> temp
    for src in mapping.keys():
        tmp = ensure_unique_temp_dir(src.parent)
        src.rename(tmp)
        temps[src] = tmp
    # Phase 2: temp -> dst
    for src, dst in mapping.items():
        tmp = temps[src]
        tmp.rename(dst)


def _clear_readonly(path: Path):
    try:
        # POSIX-Flag (mapped auf Windows ReadOnly)
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass
    # Fallback: attrib
    try:
        subprocess.run(["attrib", "-R", str(path)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _set_hidden_system(path: Path):
    try:
        subprocess.run(["attrib", "+H", "+S", str(path)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _mark_folder_customized(folder: Path):
    # Explorer beachtet desktop.ini zuverlässiger, wenn der Ordner ReadOnly ist
    try:
        subprocess.run(["attrib", "+R", str(folder)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def write_desktop_ini(folder: Path, pic_id: str) -> None:
    """
    Schreibt/ersetzt desktop.ini sicher:
      - vorhandenes ReadOnly aufheben
      - atomar ersetzen
      - Hidden+System fürs ini setzen
      - Ordner auf ReadOnly setzen (für Explorer-Custom-Icons)
    """
    folder.mkdir(parents=True, exist_ok=True)
    ini_path = folder / "desktop.ini"
    content = (
        "[.ShellClassInfo]\n"
        f"IconResource=..\\icons\\{pic_id}.ico,0\n"
        "[ViewState]\n"
        "Mode=\n"
        "Vid=\n"
        "FolderType=Music\n"
    )

    # Wenn es schon eine desktop.ini gibt: ReadOnly entfernen, damit wir ersetzen dürfen
    if ini_path.exists():
        _clear_readonly(ini_path)

    # Atomar schreiben: erst temp, dann ersetzen
    tmp_path = folder / ".__tmp_desktop.ini"
    tmp_path.write_text(content, encoding="utf-8")
    try:
        # atomar, überschreibt ReadOnly nicht -> daher vorher _clear_readonly
        os.replace(tmp_path, ini_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

    # Nach dem Schreiben wieder verstecken/system markieren
    _set_hidden_system(ini_path)
    _mark_folder_customized(folder)


def rmtree_force(path: Path):
    """Ordner rekursiv löschen; ReadOnly-Attribute vorher entfernen."""
    def onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
        except Exception:
            pass
        try:
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=onerror)


# ---------- Platzhalter für weitere Modi ----------


def renum_pics() -> int:
    """
    Bringt NUR die PNGs in ./pics auf einen lückenlosen 10er-Raster (000,010,020,...).
    icons/ und Ordner/desktop.ini werden NICHT angefasst.
    Schreibt renum_map.csv (außer im --dry-run).
    """
    findings: List[Finding] = []

    if not PICS_DIR.exists() or not PICS_DIR.is_dir():
        log(f"Erwarteter Ordner fehlt: ./{PICS_DIR}", "ERROR")
        return 2

    # 1) PNGs parsen (Schema prüfen)
    items: List[Tuple[int, str, Path]] = []  # (old_num, NAME_original, path)
    seen_ids = set()
    for p in sorted(PICS_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".png":
            continue
        base = p.stem
        parsed = parse_id_from_basename(base)
        if not parsed:
            findings.append(Finding("ERROR", "E_SCHEMA_PIC",
                            str(p), hint="Erwartet: 'NNN NAME.png'"))
            log(f"Schemafehler in pics: {p.name}", "ERROR")
            continue
        num, name = parsed
        inv = invalid_windows_name(f"{num} {name}")
        if inv:
            findings.append(Finding("ERROR", "E_INVALID_PIC_NAME",
                            str(p), hint=f"Ungültiger Name ({inv})."))
            log(f"Ungültiger PNG-Name: {p.name}", "ERROR")
            continue
        try:
            onum = int(num)
        except ValueError:
            findings.append(Finding("ERROR", "E_BAD_NUM", str(
                p), actual=num, hint="Nummer nicht numerisch."))
            log(f"Nicht-numerische Nummer: {p.name}", "ERROR")
            continue
        ident = f"{num} {name}"
        if ident in seen_ids:
            findings.append(Finding("ERROR", "E_DUP_PIC_ID", str(
                p), actual=ident, hint="Doppelter Ident-String in pics."))
            log(f"Doppelter Ident in pics: {ident}", "ERROR")
            continue
        seen_ids.add(ident)
        items.append((onum, name, p))

    if any(f.severity == "ERROR" for f in findings):
        # Report zeigen & mit Fehler raus
        return finalize(findings)

    if not items:
        log("Keine PNGs in ./pics gefunden.", "WARN")
        return 1

    # 2) Sortierung: (alte Nummer, NAME case-insensitiv/natürlich)
    items.sort(key=lambda t: (t[0], natural_sort_key_name(t[1])))

    # 3) Neue Nummern vergeben (000,010,020,...) — prüfen auf >999
    # old_num, name, path, new_num
    new_plan: List[Tuple[int, str, Path, int]] = []
    for idx, (onum, name, p) in enumerate(items):
        nnum = idx * 10
        if nnum > 999:
            log(
                f"Zu viele Dateien für 3-stellige Nummern: benötigte Nummer {nnum:03d} > 999", "ERROR")
            findings.append(Finding("ERROR", "E_OVERFLOW_3DIGIT", str(
                p), actual=str(nnum), hint="Mehr als 100 Motive. Policy notwendig."))
            return finalize(findings)
        new_plan.append((onum, name, p, nnum))

    # 4) Mapping berechnen (nur wenn sich Nummer ändert)
    renames: Dict[Path, Path] = {}
    # old_png, new_png, old_nnn, new_nnn, name
    rows_for_csv: List[Tuple[str, str, str, str, str]] = []
    for onum, name, p, nnum in new_plan:
        old_base = f"{onum:03d} {name}"
        new_base = f"{nnum:03d} {name}"
        old_path = p
        new_path = p.with_name(f"{new_base}.png")
        rows_for_csv.append(
            (f"{old_base}.png", f"{new_base}.png", f"{onum:03d}", f"{nnum:03d}", name))
        if old_path.resolve() != new_path.resolve():
            renames[old_path] = new_path

    if not renames:
        log("Renum: Keine Änderungen erforderlich (bereits im 10er-Raster).", "INFO")
        # Trotzdem Mapping-Datei schreiben? Ja, hilfreich – außer im Dry-Run.
        if not cfg.dry_run:
            with open("renum_map.csv", "w", encoding="utf-8", newline="") as fh:
                fh.write("old_png,new_png,old_nnn,new_nnn,name\n")
                for r in rows_for_csv:
                    fh.write(",".join(f'"{x}"' for x in r) + "\n")
        return 0

    # 5) Zielkollisionen prüfen (existierende Dateien, die keine Quellen sind)
    dests = set(renames.values())
    srcs = set(renames.keys())
    conflicts = []
    for dst in dests:
        if dst.exists() and dst not in srcs:
            conflicts.append(str(dst))
    if conflicts:
        log(f"Renum: Zielkollision(en) vorhanden, Abbruch:\n  " +
            "\n  ".join(conflicts), "ERROR")
        findings.append(Finding("ERROR", "E_DEST_CONFLICT", "pics", actual="; ".join(conflicts),
                                hint="Zieldatei existiert bereits und wird nicht durch einen anderen Rename freigegeben."))
        return finalize(findings)

    # 6) Dry-run: Plan anzeigen und raus
    if cfg.dry_run:
        log("Renum (dry-run) – geplanter Mapping-Plan:", "INFO")
        for onum, name, p, nnum in new_plan:
            old = f"{onum:03d} {name}.png"
            new = f"{nnum:03d} {name}.png"
            mark = " (unchanged)" if onum == nnum else ""
            log(f"  {old}  →  {new}{mark}", "INFO")
        log("(dry-run: keine Dateien umbenannt, renum_map.csv nicht geschrieben)", "INFO")
        return 0

    # 7) renum_map.csv schreiben
    try:
        with open("renum_map.csv", "w", encoding="utf-8", newline="") as fh:
            fh.write("old_png,new_png,old_nnn,new_nnn,name\n")
            for r in rows_for_csv:
                fh.write(",".join(f'"{x}"' for x in r) + "\n")
    except Exception as e:
        log(f"Fehler beim Schreiben von renum_map.csv: {e}", "ERROR")
        return 2

    # 8) Zweiphasig umbenennen
    try:
        if cfg.verbose >= 2:
            log("Beginne zweiphasige Umbenennungen...", "DEBUG")
            for s, d in renames.items():
                log(f"  {s.name}  ->  {d.name}", "DEBUG")
        two_phase_file_renames(renames)
    except Exception as e:
        log(f"Fehler beim Umbenennen: {e}", "ERROR")
        return 2

    # 9) Summary
    changed = sum(1 for onum, _, _, nnum in new_plan if onum != nnum)
    unchanged = len(new_plan) - changed
    log(f"Renum abgeschlossen: {changed} geändert, {unchanged} unverändert. Mapping in renum_map.csv.", "INFO")
    return 0


def build_icons(icon_format: Optional[str]) -> int:
    """
    Baut ALLE .ico aus den aktuellen pics/NNN NAME.png neu.
    Vorher: ./icons vollständig löschen und neu erstellen.
    - Frames 64/128/256
    - weißer Hintergrund, kein Alpha, sRGB, 8-Bit TrueColor
    - optional --icon-format bmp|png
    - respektiert --dry-run / --verbose
    """
    # Vorbedingungen
    if not PICS_DIR.exists() or not PICS_DIR.is_dir():
        log(f"Erwarteter Ordner fehlt: ./{PICS_DIR}", "ERROR")
        return 2

    im_bin = find_im_binary()
    if not im_bin:
        log("ImageMagick nicht gefunden (weder 'magick' noch 'convert' im PATH).", "ERROR")
        return 2

    # PNG-Quellen einsammeln
    sources: list[tuple[str, Path]] = []
    for p in sorted(PICS_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() == ".png":
            parsed = parse_id_from_basename(p.stem)
            if not parsed:
                log(f"Übersprungen (Schemafehler): {p.name}", "WARN")
                continue
            num, name = parsed
            invalid = invalid_windows_name(f"{num} {name}")
            if invalid:
                log(f"Übersprungen (ungültiger Name): {p.name}", "WARN")
                continue
            sources.append((f"{num} {name}", p))

    if not sources:
        log("Keine PNG-Quellen gefunden.", "WARN")
        return 1

    # --- Icons-Ordner neu erstellen ---
    if cfg.dry_run:
        if ICONS_DIR.exists() and ICONS_DIR.is_dir():
            log("[PLAN] Lösche Ordner ./icons vollständig.", "INFO")
        elif ICONS_DIR.exists():
            log("[PLAN] Pfad ./icons existiert und ist KEIN Ordner (Fehler).", "ERROR")
            return 2
        log("[PLAN] Erstelle neuen Ordner ./icons.", "INFO")
    else:
        try:
            if ICONS_DIR.exists():
                if ICONS_DIR.is_dir():
                    rmtree_force(ICONS_DIR)
                else:
                    log("Pfad ./icons existiert, ist aber kein Ordner.", "ERROR")
                    return 2
            ICONS_DIR.mkdir(parents=True, exist_ok=False)
            log("icons-Ordner neu erstellt.", "INFO")
        except Exception as e:
            log(f"icons-Ordner konnte nicht neu erstellt werden: {e}", "ERROR")
            return 2

    # Arbeitsverzeichnis für Normalisate
    tmp_root: Optional[Path] = None
    if not cfg.dry_run:
        try:
            tmp_root = make_tmpdir(Path("."))
        except Exception as e:
            log(
                f"Temporäres Arbeitsverzeichnis konnte nicht erstellt werden: {e}", "ERROR")
            return 2

    used_sizes = [64, 128, 256]  # Aufsteigend für ICO
    # (source_png, ico_file, used_sizes)
    manifest_rows: list[tuple[str, str, str]] = []

    errors = 0
    built = 0

    for ident, src_png in sources:
        out_ico = ICONS_DIR / f"{ident}.ico"
        if cfg.dry_run:
            log(f"[PLAN] Build ICO: {src_png}  →  {out_ico}", "INFO")
            if cfg.verbose >= 2:
                for s in used_sizes:
                    tmp_target = Path("<tmp>") / \
                        f"{src_png.stem}_{s}_white.png"
                    cmd = im_norm_command(im_bin, src_png, tmp_target, s)
                    log("      " + " ".join(cmd), "DEBUG")
                cmd_ico = im_ico_command(
                    im_bin,
                    [Path("<tmp>") /
                     f"{src_png.stem}_{s}_white.png" for s in used_sizes],
                    out_ico,
                    icon_format,
                )
                log("      " + " ".join(cmd_ico), "DEBUG")
            manifest_rows.append(
                (str(src_png), str(out_ico), ";".join(map(str, used_sizes))))
            continue

        # Reale Ausführung
        assert tmp_root is not None
        tmp_files: list[Path] = []
        ok_all = True

        try:
            # 1) Norm-Frames erzeugen
            for s in used_sizes:
                dst = tmp_root / f"{src_png.stem}_{s}_white.png"
                cmd = im_norm_command(im_bin, src_png, dst, s)
                if cfg.verbose >= 2:
                    log("IM> " + " ".join(cmd), "DEBUG")
                ok, err = run_im(cmd)
                if not ok or not dst.exists():
                    log(f"Fehler bei Normierung {src_png.name} @ {s}px:\n{err}", "ERROR")
                    ok_all = False
                    break
                tmp_files.append(dst)

            # 2) ICO bauen (nur wenn Normierung ok)
            if ok_all:
                tmp_out = ICONS_DIR / f".__tmp__{ident}.ico"
                cmd_ico = im_ico_command(
                    im_bin, tmp_files, tmp_out, icon_format)
                if cfg.verbose >= 2:
                    log("IM> " + " ".join(cmd_ico), "DEBUG")
                ok, err = run_im(cmd_ico)
                if not ok or not tmp_out.exists():
                    log(f"Fehler beim ICO-Build {ident}:\n{err}", "ERROR")
                    ok_all = False
                else:
                    # Atomar ersetzen (hier nur Umbenennen, da icons leer/neu ist)
                    try:
                        if out_ico.exists():
                            out_ico.unlink()
                        tmp_out.replace(out_ico)
                    except Exception as e:
                        log(f"Konnte {tmp_out.name} nicht nach {out_ico.name} verschieben: {e}", "ERROR")
                        ok_all = False
        finally:
            # 3) Cleanup der Norm-Frames (best effort)
            if tmp_files:
                for f in tmp_files:
                    try:
                        if f.exists():
                            f.unlink()
                    except Exception:
                        pass

        if ok_all:
            built += 1
            manifest_rows.append(
                (str(src_png), str(out_ico), ";".join(map(str, used_sizes))))
            log(f"[OK] {src_png.name} → {out_ico.name}  (Größen: {';'.join(map(str, used_sizes))})", "INFO")
        else:
            errors += 1

    # Globales Cleanup
    if tmp_root and tmp_root.exists():
        try:
            tmp_root.rmdir()
        except OSError:
            try:
                for child in tmp_root.glob("*"):
                    try:
                        child.unlink()
                    except Exception:
                        pass
                tmp_root.rmdir()
            except Exception:
                pass

    # Manifest schreiben (außer im Dry-Run)
    if not cfg.dry_run:
        try:
            with open("icons_manifest.csv", "w", encoding="utf-8", newline="") as fh:
                fh.write("source_png,ico_file,used_sizes\n")
                for r in manifest_rows:
                    fh.write(",".join(f'"{x}"' for x in r) + "\n")
        except Exception as e:
            log(f"Fehler beim Schreiben von icons_manifest.csv: {e}", "ERROR")
            errors += 1

    # Zusammenfassung
    if cfg.dry_run:
        log(
            f"PLAN: ./icons wird neu erstellt und {len(sources)} ICO(s) würden gebaut. (dry-run)", "INFO")
        return 0

    if errors > 0:
        log(f"FERTIG mit Fehlern: {built} OK, {errors} Fehler.", "ERROR")
        return 2

    log(f"FERTIG: {built} ICO(s) gebaut. Ordner ./icons frisch erstellt. Manifest: icons_manifest.csv", "INFO")
    return 0


def rebuild_folders() -> int:
    """
    Ordnerlandschaft nach pics/ aufbauen:
      - Matching per NAME (case-insensitiv, whitespace-normalisiert)
      - Zielname je PNG: './NNN NAME/'
      - vorhandene Ordner mit gleichem NAME auf Ziel-Index umbenennen
      - fehlende Ordner anlegen
      - ALLE desktop.ini neu schreiben
      - verwaiste Ordner warnen
    Respektiert --dry-run / --verbose.
    Nach echtem Lauf: Abschluss-Audit.
    """
    # Vorbedingungen
    if not PICS_DIR.exists() or not PICS_DIR.is_dir():
        log(f"Erwarteter Ordner fehlt: ./{PICS_DIR}", "ERROR")
        return 2

    # --- PNGs einlesen (Quelle der Wahrheit) ---
    pics: Dict[str, Tuple[str, str, Path]] = {}  # id -> (num, name, path)
    name_norm_to_id: Dict[str, str] = {}
    for p in sorted(PICS_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".png":
            continue
        parsed = parse_id_from_basename(p.stem)
        if not parsed:
            log(f"Übersprungen (Schemafehler): {p.name}", "WARN")
            continue
        num, name = parsed
        inv = invalid_windows_name(f"{num} {name}")
        if inv:
            log(f"Übersprungen (ungültiger Name): {p.name}", "WARN")
            continue
        ident = f"{num} {name}"
        pics[ident] = (num, name, p)
        nname = normalize_name(name)
        if nname in name_norm_to_id:
            # Nicht fatal, aber Hinweis: mehrere PNGs mit demselben NAME
            log(f"[HINW] Mehrere PNGs mit gleichem NAME (normalisiert): "
                f"{name_norm_to_id[nname]}  &  {ident}", "WARN")
        else:
            name_norm_to_id[nname] = ident

    if not pics:
        log("Keine PNG-Quellen gefunden.", "WARN")
        return 1

    # --- vorhandene Ordner scannen ---
    folders_by_id: Dict[str, Path] = {}
    folders_by_name_norm: Dict[str, List[str]] = defaultdict(list)
    for d in sorted(Path(".").iterdir()):
        if not d.is_dir():
            continue
        if d.name in {PICS_DIR.name, ICONS_DIR.name}:
            continue
        parsed = parse_id_from_basename(d.name)
        if not parsed:
            # Fremdordner ignorieren
            continue
        num, name = parsed
        ident = f"{num} {name}"
        folders_by_id[ident] = d
        folders_by_name_norm[normalize_name(name)].append(ident)

    # --- Plan aufstellen ---
    rename_map: Dict[Path, Path] = {}
    create_list: List[Path] = []
    ini_targets: List[str] = []       # pic_id, für die wir INI schreiben
    used_folder_ids: set[str] = set()
    warnings = 0
    errors = 0

    for pic_id, (num, name, _p) in pics.items():
        target = Path(".") / pic_id
        name_norm = normalize_name(name)

        # 1) exakter Ordner bereits vorhanden?
        if pic_id in folders_by_id:
            src = folders_by_id[pic_id]
            used_folder_ids.add(pic_id)
            if cfg.verbose:
                log(f"Ordner OK: {src} (bleibt)", "INFO")
            ini_targets.append(pic_id)
            continue

        # 2) Ordner mit gleichem NAME (andere Nummer) vorhanden?
        candidates = [fid for fid in folders_by_name_norm.get(
            name_norm, []) if fid not in used_folder_ids]
        if candidates:
            # stabil wählen: kleinste Nummer zuerst
            candidates.sort(key=lambda fid: int(fid.split(" ", 1)[0]))
            chosen_id = candidates[0]
            src = folders_by_id[chosen_id]
            used_folder_ids.add(chosen_id)

            if target.exists():
                # Ziel existiert (anderer Ordner) -> Konflikt, wir überschreiben NICHT
                log(
                    f"[KONFLIKT] Zielordner existiert bereits: {target} (Quelle: {src})", "ERROR")
                errors += 1
                # dennoch INI für pic_id auf Ziel schreiben, falls Ziel tatsächlich der richtige ist
                if pic_id in folders_by_id:
                    ini_targets.append(pic_id)
                continue

            if cfg.verbose:
                log(f"Rename: {src.name}  →  {target.name}", "INFO")
            rename_map[src] = target
            ini_targets.append(pic_id)
            continue

        # 3) Kein Ordner für diesen NAME -> neu anlegen
        if target.exists():
            # Falls der Zielname schon als Ordner/Datei existiert, aber nicht im Schema erfasst...
            log(f"[KONFLIKT] Zielname existiert bereits: {target}", "ERROR")
            errors += 1
            continue
        if cfg.verbose:
            log(f"Create: {target}", "INFO")
        create_list.append(target)
        ini_targets.append(pic_id)

    # 4) Verwaiste Ordner melden (alles, was nicht benutzt wurde)
    for fid, fpath in folders_by_id.items():
        if fid not in used_folder_ids and fid not in pics:
            log(f"[ORPHAN] Ordner ohne PNG: {fpath}", "WARN")
            warnings += 1

    # 5) Dry-run? -> Plan anzeigen und abbrechen
    if cfg.dry_run:
        if rename_map:
            log("Geplante Ordner-Umbenennungen:", "INFO")
            for s, d in rename_map.items():
                log(f"  {s}  →  {d}", "INFO")
        if create_list:
            log("Geplante Ordner-Neuanlagen:", "INFO")
            for d in create_list:
                log(f"  {d}", "INFO")
        # desktop.ini-Plan
        if cfg.verbose:
            log("desktop.ini wird für folgende IDs neu geschrieben:", "INFO")
            for pid in ini_targets:
                log(f"  {pid}  →  ..\\icons\\{pid}.ico,0", "INFO")

        # Icons prüfen (nur Warnung, falls fehlen)
        for pid in ini_targets:
            ico = ICONS_DIR / f"{pid}.ico"
            if not ico.exists():
                log(f"[WARN] Zu {pid} fehlt (noch) {ico}", "WARN")
                warnings += 1

        # Dry-run Exitcode
        if errors:
            return 2
        return 1 if warnings else 0

    # 6) Reale Ausführung
    # 6a) Umbenennen (kollisionsfrei)
    try:
        if rename_map:
            if cfg.verbose >= 2:
                log("Zweiphasige Ordner-Renames starten...", "DEBUG")
            two_phase_dir_renames(rename_map)
    except Exception as e:
        log(f"Fehler beim Umbenennen von Ordnern: {e}", "ERROR")
        return 2

    # 6b) Neu anlegen
    for d in create_list:
        try:
            d.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # Falls zwischenzeitlich entstanden: okay
            pass
        except Exception as e:
            log(f"Ordner konnte nicht angelegt werden: {d} -> {e}", "ERROR")
            errors += 1

    # 6c) Alle desktop.ini neu schreiben
    for pid in ini_targets:
        folder = Path(".") / pid
        try:
            write_desktop_ini(folder, pid)
        except Exception as e:
            log(
                f"desktop.ini konnte nicht geschrieben werden: {folder} -> {e}", "ERROR")
            errors += 1
        # fehlendes ICO nur warnen
        ico = ICONS_DIR / f"{pid}.ico"
        if not ico.exists():
            log(f"[WARN] Zu {pid} fehlt (noch) {ico}", "WARN")
            warnings += 1

    # 7) Abschluss-Audit (nur nach echtem Lauf)
    log("Starte Abschluss-Audit...", "INFO")
    rc = audit()  # schreibt audit_report.json
    # rc spiegelt bereits WARN/ERROR wider
    return rc


# ---------- Abschluss / Report ----------


def finalize(findings: List[Finding]) -> int:
    counts = Counter(f.severity for f in findings)
    # Report-Datei schreiben
    report = {
        "summary": {
            "info": counts.get("INFO", 0),
            "warn": counts.get("WARN", 0),
            "error": counts.get("ERROR", 0),
        },
        "findings": [asdict(f) for f in findings],
    }
    with open("audit_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    # Konsole zusammenfassen
    if findings:
        log(f"SUMMARY: {counts.get('INFO', 0)} INFO, {counts.get('WARN', 0)} WARN, {counts.get('ERROR', 0)} ERROR",
            "INFO")
    else:
        log("SUMMARY: 0 INFO, 0 WARN, 0 ERROR", "INFO")

    if counts.get("ERROR", 0) > 0:
        return 2
    if counts.get("WARN", 0) > 0:
        return 1
    return 0

# ---------- CLI ----------


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Audit & Verwaltung für pics/icons/Ordner (ICO-Projekt). Standard: Audit (read-only).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Nur planen/prüfen, keine Änderungen (Audit ist immer read-only).")
    p.add_argument("-v", "--verbose", action="count", default=0,
                   help="Mehr Ausgaben. -v oder -vv.")
    p.add_argument("--no-color", action="store_true",
                   help="Farbausgabe deaktivieren.")

    # Modi (mutually exclusive)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--renum-pics", action="store_true",
                   help="(Stub) PNGs auf 10er-Raster umnummerieren.")
    g.add_argument("--build-icons", action="store_true",
                   help="(Stub) Alle ICOs frisch aus pics bauen.")
    g.add_argument("--rebuild-folders", action="store_true",
                   help="(Stub) Ordnerstruktur & desktop.ini nachziehen.")
    p.add_argument("--icon-format", choices=["bmp", "png"], default=None,
                   help="(Stub) Frame-Format im ICO bei --build-icons.")

    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    cfg.verbose = int(args.verbose or 0)
    cfg.dry_run = bool(args.dry_run)
    cfg.use_color = not bool(args.no_color)

    if args.renum_pics:
        return renum_pics()
    if args.build_icons:
        return build_icons(args.icon_format)
    if args.rebuild_folders:
        return rebuild_folders()
    # Default: Audit
    return audit()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
