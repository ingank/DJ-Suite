import os
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.aifc', '.mp3', '.flac']
ARCHIV_ROOT = Path('.').resolve()


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


def find_audio_files(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                yield Path(dirpath) / name


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outfilename = f"sha256-hashes-{timestamp}.txt"
    with open(outfilename, 'w', encoding='utf-8') as out:
        for file in find_audio_files(ARCHIV_ROOT):
            try:
                sha256 = pcm_sha256_pipe(file)
                relpath = file.relative_to(ARCHIV_ROOT)
                # Bildschirm-Ausgabe:
                print(sha256)
                print(relpath.parent.as_posix())
                print(relpath.name)
                print()
                # Dateiausgabe:
                out.write(f"{sha256} {relpath.as_posix()}\n")
            except Exception as e:
                print(f"Fehler bei {file}: {e}")


if __name__ == "__main__":
    main()
