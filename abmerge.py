#!/usr/bin/env python3
"""
abmerge – A/B→C-Merger für FLAC-Bibliotheken

Zweck:
- Struktur & Dateinamen aus B
- Audiostream aus A (-c:a copy)
- Cover aus B (erstes embedded) oder Platzhalter, beidmittig Crop + Scale 600×600, attached_pic/MJPEG
- Tags: alle aus B, plus alle mx-* aus A (A überschreibt B)
- Keys lowercase (Mutagen/Projektwahrheit)
- touch_comment_tag am Ende anwenden
- Serielle Verarbeitung, harter Abbruch bei Nutzerfehlern
- Log: ./abmerge-<timestamp>.log
- CLI: abmerge [--verbose]  (keine weiteren Optionen)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# --- Projekt-Libs (werfen früh, wenn ffmpeg/ffprobe fehlen) ---
from lib import config
from lib.utils import find_audio_files, get_timestamp, make_filename
from lib import flac as flaclib

# Exit-Codes (siehe Spezifikation)
EXIT_OK = 0
EXIT_PRECONDITION = 10
EXIT_EXT_TOOLS = 11
EXIT_PAIRING = 12
EXIT_IO = 13
EXIT_INTERNAL = 20

A_DIRNAME = "A-Ordner"
B_DIRNAME = "B-Ordner"
C_DIRNAME = "C-Ordner"
MX_HASH_KEY = "mx-hash"

# --- Logging-Helfer ---------------------------------------------------------


class DualLogger:
    def __init__(self, logfile: Path, verbose_console: bool = False):
        self.logfile = logfile
        self.verbose_console = verbose_console
        self.logfile.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.logfile, "a", encoding="utf-8", newline="\n")

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass

    def _write(self, line: str, console: bool):
        ts = get_timestamp()
        line_ts = f"[{ts}] {line}"
        self._fh.write(line_ts + "\n")
        self._fh.flush()
        if console:
            print(line, flush=True)

    def status(self, line: str):
        # Immer auf Konsole + Log
        self._write(line, console=True)

    def detail(self, line: str):
        # Immer ins Log; auf Konsole nur bei --verbose
        self._write(line, console=self.verbose_console)


# --- Hilfsfunktionen --------------------------------------------------------

def fail(logger: DualLogger, code: int, msg: str) -> None:
    logger.status(f"[ERR] {msg}")
    logger.close()
    sys.exit(code)


def check_preconditions(logger: DualLogger, cwd: Path) -> Tuple[Path, Path, Path]:
    """Prüft A/B vorhanden, C nicht vorhanden; wirft harten Fehler bei Verstoß."""
    a_dir = cwd / A_DIRNAME
    b_dir = cwd / B_DIRNAME
    c_dir = cwd / C_DIRNAME

    if not a_dir.is_dir() or not b_dir.is_dir():
        fail(logger, EXIT_PRECONDITION,
             f"Voraussetzungen fehlen – erwartet Ordner '{A_DIRNAME}/' und '{B_DIRNAME}/' im Arbeitsverzeichnis")

    if c_dir.exists():
        fail(logger, EXIT_PRECONDITION,
             f"'{C_DIRNAME}/' existiert bereits – bitte entfernen/umbenennen (kein Overwrite erlaubt)")

    return a_dir, b_dir, c_dir


def discover_flacs(root: Path) -> List[Path]:
    """Relativpfade der .flac-Dateien unterhalb von root (Snapshot)."""
    return [Path(p) for p in find_audio_files(root, absolute=False, filter_ext=[".flac"])]


def read_mx_hash(file_path: Path) -> str | None:
    """Liest mx-hash (lowercase) als Einzelwert; None, wenn nicht vorhanden."""
    try:
        val = flaclib.get_tags(file_path, MX_HASH_KEY)
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None
    except Exception:
        return None


def pair_by_hash(
    a_root: Path, b_root: Path, a_files: List[Path], b_files: List[Path]
) -> List[Tuple[str, Path, Path]]:
    """Erzeugt Liste (hash, a_rel, b_rel); validiert 1:1, sortiert nach b_rel. Hartabbruch bei Verstoß."""
    # A: hash -> a_rel
    a_map: Dict[str, Path] = {}
    for rel in a_files:
        h = read_mx_hash(a_root / rel)
        if not h:
            raise ValueError(
                f"fehlender oder leerer {MX_HASH_KEY} in A: {rel}")
        if h in a_map:
            raise ValueError(
                f"mehrfacher {MX_HASH_KEY} in A: {h} für {a_map[h]} und {rel}")
        a_map[h] = rel

    # B: hash -> b_rel
    b_map: Dict[str, Path] = {}
    for rel in b_files:
        h = read_mx_hash(b_root / rel)
        if not h:
            raise ValueError(
                f"fehlender oder leerer {MX_HASH_KEY} in B: {rel}")
        if h in b_map:
            raise ValueError(
                f"mehrfacher {MX_HASH_KEY} in B: {h} für {b_map[h]} und {rel}")
        b_map[h] = rel

    # 1:1 Validierung
    if set(a_map.keys()) != set(b_map.keys()):
        missing_in_b = sorted(set(a_map.keys()) - set(b_map.keys()))
        missing_in_a = sorted(set(b_map.keys()) - set(a_map.keys()))
        parts = []
        if missing_in_b:
            parts.append(f"{len(missing_in_b)} Hash(es) ohne Pendant in B")
        if missing_in_a:
            parts.append(f"{len(missing_in_a)} Hash(es) ohne Pendant in A")
        raise ValueError("1:1-Paarbildung verletzt: " +
                         "; ".join(parts) if parts else "unbekannter Fehler")

    pairs = [(h, a_map[h], b_map[h]) for h in b_map.keys()]
    # stabil & deterministisch: nach Pfad in B
    pairs.sort(key=lambda t: t[2].as_posix().lower())
    return pairs


def build_ffmpeg_cmd(
    a_src: Path,
    b_src: Path,
    c_tmp: Path,
    a_cover_idx: int | None,
    b_cover_idx: int | None,
    placeholder_path: Path,
) -> list[str]:
    """
    Input 0: A  (Audio immer von hier; evtl. Cover-Fallback)
    Input 1: B  (Tags IMMER von hier; evtl. Cover)
    Input 2: Platzhalter  (nur wenn weder B noch A ein Cover hat)
    """
    cmd: list[str] = ["ffmpeg", "-v", "error"]

    # Inputs
    cmd += ["-i", str(a_src)]  # 0 = A
    cmd += ["-i", str(b_src)]  # 1 = B
    use_placeholder = (b_cover_idx is None and a_cover_idx is None)
    if use_placeholder:
        cmd += ["-i", str(placeholder_path)]  # 2 = Platzhalter

    # Audio aus A (copy)
    cmd += ["-map", "0:a:0", "-c:a", "copy"]

    # Cover-Pfadwahl: zuerst B, dann A, sonst Platzhalter
    if b_cover_idx is not None:
        cmd += ["-map", f"1:{b_cover_idx}"]
        vf = "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600"
    elif a_cover_idx is not None:
        cmd += ["-map", f"0:{a_cover_idx}"]
        vf = "crop='min(iw,ih)':'min(iw,ih)':'(iw-min(iw,ih))/2':'(ih-min(iw,ih))/2',scale=600:600"
    else:
        cmd += ["-map", "2:v:0"]
        vf = "scale=600:600"

    cmd += ["-vf", vf, "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
    cmd += ["-metadata:s:v:0", "title=Front Cover"]
    cmd += ["-metadata:s:v:0", "comment=Cover (front)"]

    # Tags IMMER aus B
    cmd += ["-map_metadata", "1"]

    # FLAC-Muxer explizit (wegen .partial)
    cmd += ["-f", "flac", "-y", str(c_tmp)]
    return cmd


def get_cover_index(b_src: Path) -> int | None:
    """
    Liefert den *globalen* Stream-Index des ersten embedded Covers in B
    (wie lib.flac._first_attached_pic_index). None, wenn keins vorhanden.
    """
    info = flaclib._ffprobe_json(b_src)
    return flaclib._first_attached_pic_index(info)


def set_mx_tags_from_a_on_target(a_src: Path, target: Path) -> int:
    """Liest alle mx-* aus A (lowercase) und schreibt sie (overwrite=True) auf target. Gibt Anzahl Keys zurück."""
    all_a = flaclib.get_tags(a_src)  # dict: key(lower) -> list[str]
    if not isinstance(all_a, dict):
        return 0
    mx_map: Dict[str, str] = {}
    for k, v in all_a.items():
        if not isinstance(k, str):
            continue
        kl = k.lower()
        if not kl.startswith("mx-"):
            continue
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            if not v:
                continue
            val = v[0]
        else:
            val = v
        if val is None:
            continue
        s = str(val).strip()
        if s == "":
            continue
        mx_map[kl] = s

    if mx_map:
        flaclib.set_tags(target, mx_map, overwrite=True)
    return len(mx_map)


def process_pair(
    logger: DualLogger,
    a_root: Path,
    b_root: Path,
    c_root: Path,
    h: str,
    a_rel: Path,
    b_rel: Path,
) -> None:
    a_src = a_root / a_rel
    b_src = b_root / b_rel
    c_target = c_root / b_rel
    c_target.parent.mkdir(parents=True, exist_ok=True)

    if c_target.exists():
        fail(logger, EXIT_IO, f"target exists bereits: {c_target}")

    # Temp-Datei (atomar)
    c_tmp = c_target.with_suffix(c_target.suffix + ".partial")

    # Cover-Indices beider Quellen bestimmen
    b_cover_idx = get_cover_index(b_src)
    a_cover_idx = get_cover_index(a_src)
    placeholder = Path(config.EMPTY_COVER)

    # ffmpeg-Kommando bauen (Inputs: 0=A, 1=B, optional 2=Platzhalter)
    cmd = build_ffmpeg_cmd(
        a_src=a_src,
        b_src=b_src,
        c_tmp=c_tmp,
        a_cover_idx=a_cover_idx,
        b_cover_idx=b_cover_idx,
        placeholder_path=placeholder,
    )

    # Fürs Log hübsch quoten
    cmd_str = " ".join(subprocess.list2cmdline([x]) for x in cmd)

    # Status + Details
    logger.status(
        f"[DO] hash={h}  B=\"{b_rel.as_posix()}\"  →  C=\"{(Path(C_DIRNAME) / b_rel).as_posix()}\""
    )
    logger.detail(f"ffmpeg: {cmd_str}")

    # ffmpeg ausführen
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        fail(logger, EXIT_EXT_TOOLS, "ffmpeg nicht gefunden (PATH prüfen)")
    except Exception as e:
        fail(logger, EXIT_INTERNAL, f"ffmpeg-Start fehlgeschlagen: {e}")

    if proc.returncode != 0:
        err_preview = (proc.stderr or "").strip().splitlines()[-5:]
        logger.detail("ffmpeg stderr (tail): " + " | ".join(err_preview))
        fail(logger, EXIT_INTERNAL,
             f"ffmpeg returned {proc.returncode} für B=\"{b_rel.as_posix()}\"")

    # mx-* aus A auf Ergebnis schreiben (überschreibt ggf. B)
    wrote = set_mx_tags_from_a_on_target(a_src, c_tmp)

    # touch_comment_tag am Ende
    try:
        flaclib.touch_comment_tag(c_tmp)
    except Exception as e:
        fail(logger, EXIT_INTERNAL, f"touch_comment_tag fehlgeschlagen: {e}")

    # Atomar finalisieren
    try:
        os.replace(c_tmp, c_target)
    except Exception as e:
        try:
            if c_tmp.exists():
                c_tmp.unlink()
        except Exception:
            pass
        fail(logger, EXIT_IO, f"Zielschreiben fehlgeschlagen: {e}")

    # Abschlusszeile
    if b_cover_idx is not None:
        cover_src = f"B:embedded(idx={b_cover_idx})"
    elif a_cover_idx is not None:
        cover_src = f"A:embedded(idx={a_cover_idx})"
    else:
        cover_src = "placeholder"

    logger.status(
        f"[OK]  hash={h}  B=\"{b_rel.as_posix()}\"  C=\"{(Path(C_DIRNAME) / b_rel).as_posix()}\"  "
        f"audio:A=\"{a_rel.as_posix()}\"(copy)  cover={cover_src}(600x600)  "
        f"tags:B=all + A=mx-* overwrite  wrote={wrote}"
    )


# --- main -------------------------------------------------------------------

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="abmerge",
        description="Mergt A-Ordner und B-Ordner zu C-Ordner (Audio aus A, Namen/Tags aus B, Cover aus B oder Platzhalter).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Zusätzlich das komplette ffmpeg-Kommando auf der Konsole ausgeben (im Log ist es immer enthalten).",
    )
    parser.add_argument("--version", action="version", version="abmerge 1.0")
    args = parser.parse_args(argv)

    # Logfile vorbereiten
    log_path = Path(f"./abmerge-{get_timestamp()}.log").resolve()
    logger = DualLogger(logfile=log_path, verbose_console=args.verbose)
    logger.status(
        f"[INFO] abmerge start  cwd={Path('.').resolve()}  log={log_path}")

    try:
        # Preconditions (ffmpeg/ffprobe werden bereits bei import config geprüft)
        a_root, b_root, c_root = check_preconditions(
            logger, Path(".").resolve())

        # Discovery
        a_files = discover_flacs(a_root)
        b_files = discover_flacs(b_root)
        logger.status(
            f"[INFO] gefunden: A={len(a_files)} .flac  B={len(b_files)} .flac")

        # Pairing 1:1 via mx-hash
        try:
            pairs = pair_by_hash(a_root, b_root, a_files, b_files)
        except ValueError as e:
            fail(logger, EXIT_PAIRING, f"Nutzerfehler in der Paarbildung: {e}")

        # C-Ordner anlegen
        try:
            c_root.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            fail(logger, EXIT_PRECONDITION,
                 f"'{C_DIRNAME}/' existiert bereits")
        except Exception as e:
            fail(logger, EXIT_IO, f"Kann '{C_DIRNAME}/' nicht anlegen: {e}")

        # Verarbeitung (seriell)
        for h, a_rel, b_rel in pairs:
            process_pair(logger, a_root, b_root, c_root, h, a_rel, b_rel)

        logger.status(f"[DONE] erfolgreich: {len(pairs)} Datei(en) gemerged.")
        logger.close()
        sys.exit(EXIT_OK)

    except SystemExit:
        # bereits handled
        raise
    except RuntimeError as e:
        # z. B. aus lib.flac/_ffprobe_json
        fail(logger, EXIT_INTERNAL, f"Runtime-Fehler: {e}")
    except Exception as e:
        fail(logger, EXIT_INTERNAL, f"Unerwarteter Fehler: {e}")


if __name__ == "__main__":
    main()
