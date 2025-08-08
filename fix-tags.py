# fix-tags.py

from pathlib import Path
import subprocess

from lib.utils import get_timestamp, find_audio_files
from lib.config import AUDIO_EXTENSIONS
from lib.tagging import touch_comment

# Arbeitsverzeichnis (Quellordner)
SOURCE_ROOT = Path.cwd()

# Zielverzeichnis: eine Ebene darüber
TIMESTAMP = get_timestamp()
TARGET_ROOT = (SOURCE_ROOT / f"fix-tags-{TIMESTAMP}").resolve()
TARGET_ROOT.mkdir(parents=True, exist_ok=True)

# Temporäre Cover-Dateien
TEMP_COVER_JPG = Path("_temp_cover.jpg")
TEMP_COVER_PNG = Path("_temp_cover.png")

# Snapshot aller relevanten Dateien
audio_files = find_audio_files(SOURCE_ROOT, absolute=False, generating=False)

for rel_path in audio_files:
    if rel_path.suffix.lower() != ".flac":
        continue

    src_path = SOURCE_ROOT / rel_path
    dst_path = TARGET_ROOT / rel_path
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cover extrahieren
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(src_path),
        "-an", "-vcodec", "copy",
        str(TEMP_COVER_JPG)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Cover skalieren & konvertieren
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(TEMP_COVER_JPG),
        "-vf", "scale='min(1024,iw)':'min(1024,ih)'",
        str(TEMP_COVER_PNG)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Originalbild entfernen
    subprocess.run([
        "metaflac",
        "--remove", "--block-type=PICTURE",
        str(src_path)
    ], check=True)

    # 4. Neues Cover einfügen
    subprocess.run([
        "metaflac",
        f"--import-picture-from={TEMP_COVER_PNG}",
        str(src_path)
    ], check=True)

    # 5. Remux
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(src_path),
        "-c:a", "copy",
        str(dst_path)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. COMMENT fixen
    touch_comment(dst_path)

    # 7. Ausgabe
    print(f"remuxed: {rel_path} -> {dst_path.relative_to(TARGET_ROOT)}")

# Cleanup
TEMP_COVER_JPG.unlink(missing_ok=True)
TEMP_COVER_PNG.unlink(missing_ok=True)
