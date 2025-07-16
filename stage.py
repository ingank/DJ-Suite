import os
import hashlib
import subprocess
from pathlib import Path
import argparse
import shutil
from datetime import datetime
from mutagen.flac import FLAC
import getpass

AUDIO_EXTENSIONS = {'.wav', '.aiff', '.aifc', '.mp3', '.flac'}


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
    user = getpass.getuser()
    time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Windows: User Music
    stage_dir = Path(os.path.expandvars(
        f"%USERPROFILE%/Music/STAGE/{time_str}"))
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
        flac_file.save()


def convert_to_flac(src, dst_flac, mp3_mode=False):
    # MP3 → FLAC: Immer 16 Bit, soxr-Resampler, Dither aktiviert
    # Andere Formate: Original-Bittiefe, soxr-Resampler
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', str(src),
        '-vn', '-c:a', 'flac'
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


def main():
    parser = argparse.ArgumentParser(
        description="Findet Audiodateien, gibt Pfad und 24/96 SHA256 aus. "
                    "Optional zeigt --filenames_from HASHFILE zugehörige Original-Files an."
    )
    parser.add_argument('--filenames_from', metavar='HASHFILE', type=str,
                        help='Wenn gesetzt: gibt zu passenden Hashes den Original-Filenamen aus')
    args = parser.parse_args()

    hash_lookup = {}
    if args.filenames_from:
        hash_lookup = load_hashfile(args.filenames_from)

    stage_dir = ensure_stage_folder()

    print(f"Kopiere/kodiere alle Audiodateien nach: {stage_dir}\n")

    for filepath in scan_audio_files('.'):
        print(filepath.as_posix())
        try:
            sha256 = pcm_sha256_pipe(filepath)
            print(f"  GEN0-SHA256: {sha256}")
            if hash_lookup and sha256 in hash_lookup:
                print(f"  GEN0-FILE:  {hash_lookup[sha256]}")

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
        except Exception as e:
            print(f"  [Fehler: {e}]")


if __name__ == "__main__":
    main()
