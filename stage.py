import os
import hashlib
import subprocess
from pathlib import Path
import argparse
import shutil
from datetime import datetime
from mutagen.flac import FLAC
import getpass
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "djs-config.yaml"
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
AUDIO_EXTENSIONS = cfg["audio_extensions"]
ARCHIV_ROOT = os.path.expanduser(cfg["archiv_root"])
STAGE_ROOT = os.path.expanduser(cfg["stage_root"])
ENGINE_BASE = os.path.expanduser(cfg["engine_base"])


def is_audio_file(filename):
    return Path(filename).suffix.lower() in AUDIO_EXTENSIONS


def scan_audio_files(startdir='.'):
    for dirpath, _, filenames in os.walk(startdir):
        for name in filenames:
            if is_audio_file(name):
                yield Path(dirpath) / name


def pcm_sha256_pipe(file):
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(file),
        '-map', '0:a:0',
        '-vn', '-acodec', 'pcm_s24le', '-ar', '96000', '-ac', '2',
        '-f', 's24le', '-'
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    hasher = hashlib.sha256()
    while True:
        chunk = proc.stdout.read(1024 * 1024)
        if not chunk:
            break
        hasher.update(chunk)
    proc.wait()
    return hasher.hexdigest()


def load_hashfile(hashfile_path):
    hash_to_file = {}
    with open(hashfile_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and len(parts[0]) == 64:
                sha, fname = parts
                hash_to_file[sha] = fname
    return hash_to_file


def ensure_stage_folder():
    time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    stage_dir = Path(STAGE_ROOT) / "INPUT" / time_str
    stage_dir.mkdir(parents=True, exist_ok=True)
    return stage_dir


def ensure_flac_comment_tag(file):
    """
    Korrigiert Kommentar-Tag für FLAC-Kompatibilität:
    Falls das Feld 'description' existiert,
    wird dessen Inhalt ins Standardfeld 'COMMENT' übertragen.
    Dadurch ist der Kommentar in allen Playern und Tag-Editoren sichtbar.
    """
    flac_file = FLAC(file)
    if "description" in flac_file:
        flac_file["COMMENT"] = flac_file["description"]
        del flac_file["description"]
        flac_file.save()


def convert_to_flac(src, dst_flac, mp3_mode=False):
    # MP3 → FLAC: Immer 16 Bit, soxr-Resampler, Dither aktiviert
    # Andere Formate: Original-Bittiefe, soxr-Resampler
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(src),
        '-c:a', 'flac'
    ]
    if mp3_mode:
        # 16 Bit + soxr-Resampler + Dither!
        ffmpeg_cmd.extend([
            '-sample_fmt', 's16',
            '-af', 'aresample=resampler=soxr:dither_method=shibata'
        ])
    else:
        # soxr-Resampler für beste Qualität
        ffmpeg_cmd.extend([
            '-af', 'aresample=resampler=soxr'
        ])
    ffmpeg_cmd.append(str(dst_flac))
    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)


def original_format_for_tag(orig_filepath):
    # orig_filepath ist ein string oder Path
    return Path(orig_filepath).suffix.lower().lstrip('.') if orig_filepath else ''


def set_flac_tags(flac_path, sha256, orig_file):
    audio = FLAC(flac_path)
    audio["GEN0-SHA256"] = sha256
    orig_ext = original_format_for_tag(orig_file)
    audio["GEN0-FORMAT"] = orig_ext
    audio.save()


def main():
    parser = argparse.ArgumentParser(
        description="Findet Audiodateien, kopiert oder konvertiert sie nach FLAC, "
                    "berechnet einen 24/96 PCM SHA256-Hash, "
                    "und taggt GEN0-SHA256 sowie das Ursprungsformat (GEN0-FORMAT). "
                    "Optional kann mit --filenames_from HASHFILE für bereits bekannte Hashes "
                    "der Original-Dateiname angezeigt werden (für Rückwärtskompatibilität)."
    )
    parser.add_argument('--filenames_from', metavar='HASHFILE', type=str,
                        help='Wenn gesetzt: zeigt zu passenden Hashes den Original-Dateinamen an (legacy). '
                             'Die FLACs enthalten immer das Ursprungsformat im Tag GEN0-FORMAT.')
    args = parser.parse_args()

    hash_lookup = {}
    if args.filenames_from:
        hash_lookup = load_hashfile(args.filenames_from)

    stage_dir = ensure_stage_folder()

    print(f"Kopiere/kodiere alle Audiodateien nach: {stage_dir}\n")

    for filepath in scan_audio_files('.'):
        print(filepath.as_posix())
        try:
            orig_filepath = filepath
            sha256 = pcm_sha256_pipe(filepath)
            print(f"  GEN0-SHA256: {sha256}")
            if hash_lookup and sha256 in hash_lookup:
                orig_filepath = hash_lookup[sha256]
                print(
                    f"  [Hashfile: Ursprungs-Dateiname: {hash_lookup[sha256]}]")

            # Zielpfad (Dateiname bleibt, immer .flac)
            target = stage_dir / (filepath.stem + ".flac")
            if filepath.suffix.lower() == ".flac":
                shutil.copy2(filepath, target)
                print(f"  [Kopiert als FLAC: {target.name}]")
            else:
                if filepath.suffix.lower() == ".mp3":
                    convert_to_flac(filepath, target, mp3_mode=True)
                else:
                    convert_to_flac(filepath, target)
                print(f"  [Konvertiert zu FLAC: {target.name}]")
            # Kommentar-Tag kopieren
            ensure_flac_comment_tag(target)
            set_flac_tags(target, sha256, str(orig_filepath))
        except Exception as e:
            print(f"  [Fehler: {e}]")


if __name__ == "__main__":
    main()
