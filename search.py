"""
search.py

Durchsucht rekursiv das aktuelle Verzeichnis nach Audiodateien,
erstellt SHA256-Hashes des 16bit PCM-RAW-Streams (wie in stage.py),
und schreibt: sha256 // Dateiname // Unterordner (relativ) in data.txt
"""

import os
import hashlib
import subprocess
import tempfile
from pathlib import Path

AUDIO_EXTENSIONS = ['.wav', '.aiff', '.mp3', '.flac']
IN_DIR = Path('.').resolve()
DATA_FILE = IN_DIR / "data.txt"


def pcm_sha256(file):
    """SHA256 über 16bit PCM-RAW (wie in stage.py)."""
    with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as tmpfile:
        tmp_raw = tmpfile.name
    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', str(file),
            '-map', '0:a:0',
            '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
            '-f', 's16le', tmp_raw
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        with open(tmp_raw, 'rb') as f:
            sha256_hex = hashlib.sha256(f.read()).hexdigest()
        return sha256_hex
    finally:
        if os.path.exists(tmp_raw):
            os.remove(tmp_raw)


def find_audio_files(root):
    """Rekursiv nach allen unterstützten Audio-Dateien suchen."""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                yield Path(dirpath) / name


def main():
    with open(DATA_FILE, 'w', encoding='utf-8') as out:
        for file in find_audio_files(IN_DIR):
            try:
                sha256 = pcm_sha256(file)
                relpath = file.relative_to(IN_DIR)
                filename = file.name
                folder = relpath.parent.as_posix()  # Unterordner relativ zum Startverzeichnis
                # Falls Datei im Hauptverzeichnis liegt: leeres Feld für Unterordner
                folder = folder if folder != '.' else ''
                line = f"{sha256} // {filename} // {folder}"
                print(line)
                out.write(line + "\n")
            except Exception as e:
                print(f"Fehler bei {file}: {e}")

    print(f"Alle Hashes gespeichert in {DATA_FILE}")


if __name__ == "__main__":
    main()
