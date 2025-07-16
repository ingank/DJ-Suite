import os
import hashlib
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import sys

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.aifc', '.mp3', '.flac']
ARCHIV_ROOT = Path('.').resolve()  # aktuelles Verzeichnis als Archiv
INDEX_FILE = ARCHIV_ROOT / "originals_hashindex.txt"

# Commandline-Option prüfen
HASH_ONLY = '--hash-only' in sys.argv

if not HASH_ONLY:
    MUSIC_STAGE = Path.home() / "Music" / "STAGE"
    TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    GEN1_DIR = MUSIC_STAGE / TIMESTAMP
    GEN1_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nGEN1-Arbeitskopien werden in {GEN1_DIR} abgelegt.\n")
else:
    print("\nNur Hash-Index wird erzeugt (Option --hash-only aktiv).\n")


def pcm_sha256(file):
    """SHA256 über 24bit 96kHz PCM (Stereo) aus Datei (wie besprochen)."""
    with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as tmpfile:
        tmp_raw = tmpfile.name
    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', str(file),
            '-map', '0:a:0',
            '-vn', '-acodec', 'pcm_s24le', '-ar', '96000', '-ac', '2',
            '-f', 's24le', tmp_raw
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        with open(tmp_raw, 'rb') as f:
            sha256_hex = hashlib.sha256(f.read()).hexdigest()
        return sha256_hex
    finally:
        if os.path.exists(tmp_raw):
            os.remove(tmp_raw)


def find_audio_files(root):
    """Rekursiv alle unterstützten Audiodateien finden."""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                yield Path(dirpath) / name


def make_gen1_flac(src_file, dst_dir):
    """Konvertiert Datei nach 24/96 FLAC und speichert sie im Zielordner."""
    out_flac = dst_dir / (src_file.stem + ".flac")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src_file),
        "-ar", "96000", "-ac", "2",
        "-sample_fmt", "s32",
        "-af", "aresample=resampler=soxr",
        str(out_flac)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return out_flac


def main():
    # Zeitstempel ein einziges Mal setzen
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    with open(INDEX_FILE, 'a', encoding='utf-8') as out:
        for file in find_audio_files(ARCHIV_ROOT):
            try:
                sha256 = pcm_sha256(file)
                relpath = file.relative_to(ARCHIV_ROOT).as_posix()
                # Indexzeile: sha256 @@ Zeit @@ relativer Pfad
                line = f"{sha256} @@ {timestamp} @@ {relpath}"
                print("Index:", line)
                out.write(line + "\n")
                if not HASH_ONLY:
                    # GEN1-Arbeitskopie erzeugen
                    gen1_file = make_gen1_flac(file, GEN1_DIR)
                    print(f"GEN1 erzeugt: {gen1_file.name}")
            except Exception as e:
                print(f"Fehler bei {file}: {e}")

    if not HASH_ONLY:
        print(f"\nFertig. Alle GEN1-Dateien unter {GEN1_DIR}")
    else:
        print("\nNur Hash-Index wurde erzeugt.")


if __name__ == "__main__":
    main()
