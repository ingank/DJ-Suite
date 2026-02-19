# lib/utils.py

import os
import re
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime
from lib.config import AUDIO_EXTENSIONS


def get_timestamp():
    """
    Gibt einen aktuellen Zeitstempel als String im Format YYYY-mm-dd_HH-MM-SS zurück.
    Beispiel: 2024-07-17_19-35-01
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def make_filename(
    prefix: str,
    ext: str = "txt",
    suffix: Optional[str] = None,
    dir: Optional[str] = None,
    timestamp_format: str = "%Y%m%d-%H%M%S"
) -> Path:
    """
    Erstellt einen Dateinamen wie <prefix>-<timestamp>[-<suffix>].<ext>
    Optional im Verzeichnis dir.
    Beispiel: make_filename("hash-match") -> Path('hash-match-20240723-213350.txt')
    """
    ts = datetime.now().strftime(timestamp_format)
    name = f"{prefix}-{ts}"
    if suffix:
        name += f"-{suffix}"
    name += f".{ext.lstrip('.')}"
    if dir:
        return Path(dir) / name
    return Path(name)


def find_audio_files(root, absolute: bool = False, depth: Optional[int] = None, filter_ext=None):
    """
    Gibt eine LISTE aller Audiodateien (Snapshot) unterhalb von root zurück.
    - Standard: RELATIVE Pfade (absolute=False)
    - depth: maximale Verzeichnistiefe (None = unbegrenzt)
    - filter_ext: Liste erlaubter Endungen (z. B. [".flac", ".mp3"]), sonst AUDIO_EXTENSIONS
    """
    root = Path(root).resolve()
    root_depth = len(root.parts)
    filter_set = set(ext.lower() for ext in (filter_ext or AUDIO_EXTENSIONS))

    results = []
    for dirpath, _, filenames in os.walk(root):
        curr_depth = len(Path(dirpath).parts) - root_depth
        if depth is not None and curr_depth > depth:
            continue
        for name in filenames:
            file = (Path(dirpath) / name).resolve()
            if file.suffix.lower() in filter_set:
                results.append(file if absolute else file.relative_to(root))
    return results


def loudness(file: Path) -> tuple[float | None, float | None]:
    """
    Misst LUFS und Loudness Range (LRA) mit ffmpeg-ebur128-Filter.
    Gibt Lautheitswert und Dynamik als Tuple zurück.
    LUFS wird auf Basis der gesamten Datei berechnet.
    Liefert Werte wie z. B. (-13.7, 8.2)
    """
    ffmpeg_cmd = [
        'ffmpeg', '-hide_banner', '-nostats',
        '-i', str(file),
        '-map', '0:a:0',
        '-af', 'ebur128',
        '-f', 'null', '-'
    ]
    result = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace"
    )
    stderr = result.stderr
    lufs = lra = None
    in_summary = False

    for line in stderr.splitlines():
        if 'Summary:' in line:
            in_summary = True
        elif in_summary and 'I:' in line and 'LUFS' in line:
            m = re.search(r'I:\s*(-?\d+\.\d+)\s*LUFS', line)
            if m:
                lufs = float(m.group(1))
        elif in_summary and 'LRA:' in line and 'LU' in line:
            m = re.search(r'LRA:\s*(-?\d+\.\d+)\s*LU', line)
            if m:
                lra = float(m.group(1))
        if in_summary and (lufs is not None) and (lra is not None):
            break
    return lufs, lra


def collect_audio_stats(root=".", extensions=None, depth=None, absolute=False, all_folders=False):
    """
    Zählt Audiodateien unterhalb von `root` in einem eigenen os.walk-Durchlauf.

    Args:
        root (str | Path): Startverzeichnis.
        extensions (Iterable[str] | None): erlaubte Suffixe (inkl. führendem Punkt).
            Default: lib.config.KNOWN_AUDIO_EXTENSIONS.
        depth (int | None): maximale Tiefe relativ zu `root` (None = unbegrenzt).
        absolute (bool): True = absolute Pfade in den Ergebnissen/Listen, sonst relative.
        all_folders (bool): Wenn True, enthält per_folder auch Ordner mit 0 Treffern (bis depth).

    Returns:
        dict: {
            "total": int,
            "per_ext": dict[str, int],
            "per_folder": dict[str, int],
            "duplicates": dict[str, list[str]],
        }
    """
    from lib.config import KNOWN_AUDIO_EXTENSIONS  # lazy import

    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Startverzeichnis nicht gefunden: {root}")

    # Ext-Menge normalisieren
    exts = set(extensions or KNOWN_AUDIO_EXTENSIONS)
    exts = {(e if str(e).startswith('.') else f'.{e}').lower() for e in exts}

    total = 0
    per_ext: dict[str, int] = {}
    per_folder: dict[str, int] = {}
    name_map: dict[str, list[str]] = {}

    root_depth = len(root.parts)
    seen_dirs: set[Path] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        curr_depth = len(Path(dirpath).parts) - root_depth
        if depth is not None and curr_depth > depth:
            dirnames[:] = []  # Abstieg stoppen
            continue

        dpath = Path(dirpath)
        seen_dirs.add(dpath)

        for name in filenames:
            p = dpath / name
            suffix = p.suffix.lower()
            if suffix not in exts:
                continue

            total += 1
            per_ext[suffix] = per_ext.get(suffix, 0) + 1

            folder_key_path = p.parent
            if absolute:
                folder_key = str(folder_key_path)
            else:
                folder_key = str(folder_key_path.relative_to(
                    root)) if folder_key_path != root else "."

            per_folder[folder_key] = per_folder.get(folder_key, 0) + 1

            stem_key = p.stem.casefold()
            path_str = str(p) if absolute else str(p.relative_to(root))
            name_map.setdefault(stem_key, []).append(path_str)

    if all_folders:
        for d in seen_dirs:
            if absolute:
                k = str(d)
            else:
                k = str(d.relative_to(root)) if d != root else "."
            per_folder.setdefault(k, 0)

    duplicates = {k: v for k, v in name_map.items() if len(v) > 1}

    return {
        "total": total,
        "per_ext": dict(sorted(per_ext.items(), key=lambda kv: (-kv[1], kv[0]))),
        "per_folder": dict(sorted(per_folder.items(), key=lambda kv: kv[0])),
        "duplicates": dict(sorted(duplicates.items(), key=lambda kv: kv[0])),
    }


def mirror_folder(src_dir, dst_dir, *, exclude_exts, depth: Optional[int] = None):
    """
    Spiegelt einen Ordner rekursiv per **Robocopy** nach `dst_dir`, schließt dabei
    bestimmte Dateiendungen aus und übernimmt Daten, Attribute und Zeitstempel.

    Args:
        src_dir (str | Path): Quellordner.
        dst_dir (str | Path): Zielordner.
        exclude_exts (Iterable[str]): Liste von Endungen (mit führendem Punkt), die
            NICHT kopiert/gelöscht werden sollen (z. B. [".flac"]).
        depth (int | None): maximale Verzeichnistiefe relativ zu `src_dir`.
            Wird auf Robocopy `/LEV:` gemappt (Robocopy zählt die Wurzelebene mit,
            daher verwenden wir `depth + 1`).

    Raises:
        RuntimeError: wenn das OS nicht Windows ist, Robocopy nicht gefunden wird,
                      das Ziel im Quellordner liegt oder Robocopy mit Fehler endet.
    """
    import shutil as _shutil
    import platform as _platform
    import subprocess as _subprocess

    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)

    # Guards
    if _platform.system().lower() != "windows":
        raise RuntimeError("--mirror benötigt Robocopy unter Windows")
    if _shutil.which("robocopy") is None:
        raise RuntimeError("Robocopy nicht im PATH gefunden (erforderlich)")

    # Sicherheitsgeländer: Ziel darf nicht innerhalb der Quelle liegen
    try:
        src_res = src_dir.resolve()
        dst_res = dst_dir.resolve()
        if str(dst_res).startswith(str(src_res) + os.sep):
            raise RuntimeError(
                "Zielordner darf nicht innerhalb des Quellordners liegen")
    except Exception:
        # Wenn resolve() fehlschlägt, lassen wir Robocopy später scheitern.
        pass

    dst_dir.mkdir(parents=True, exist_ok=True)

    # robocopy <SRC> <DST> /MIR [/LEV:n] [/XF *.ext ...] + leise Flags
    cmd = ["robocopy", str(src_dir), str(dst_dir), "/MIR"]

    # Tiefe mappen: --depth=N -> /LEV:(N+1) (Robocopy zählt Wurzelebene als 1)
    if depth is not None:
        lev = max(0, int(depth)) + 1
        cmd.append(f"/LEV:{lev}")

    # Excludes: zu *.ext Maske transformieren
    xf_parts = []
    for ext in (exclude_exts or []):
        ext = str(ext).strip()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        xf_parts.append(f"*.{ext.lstrip('.')}")
    if xf_parts:
        cmd.append("/XF")
        cmd.extend(xf_parts)

    # Leise & deterministisch: keine Retries, keine Progress-Noise
    cmd += ["/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"]

    # Ausführen
    proc = _subprocess.run(cmd, capture_output=True, text=True)
    rc = proc.returncode

    # Robocopy: 0..7 = Erfolg, >7 = Fehler
    if rc <= 7:
        return {"ok": True, "exit_code": rc}

    # Fehler – hilfreiche Meldung
    msg = [
        "Robocopy fehlgeschlagen",
        f"ExitCode={rc}",
        "Kommando: " + " ".join(cmd),
    ]
    if proc.stdout:
        msg.append("STDOUT:\n" + proc.stdout)
    if proc.stderr:
        msg.append("STDERR:\n" + proc.stderr)
    raise RuntimeError("\n".join(msg))
