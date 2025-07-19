"""
stage.py

Konvertiert alle Audiodateien im aktuellen Ordner (rekursiv) ins Stage-Format (FLAC).
- Ziel ist immer ein Zeitstempel-Ordner unterhalb von STAGE_ROOT.
- Mit Option --use-hashfile <HASHFILE>:
    * SHA256 jeder Datei wird in Hashfile gesucht.
    * Bei Treffer: Format-Endung aus Hashfile-Filename für Tagging genutzt, grün markiert.
    * Mehrfach-Treffer: weitere Namen blau gelistet.
    * Kein Treffer: lokale Endung genutzt, rote Warnung.
- Jeder Track erhält SHA256- und Format-Tag (GEN0-SHA256, GEN0-FORMAT) sowie saubere Kommentar-Tags.
- Fehler führen zum sofortigen Abbruch und Statusmeldung.
"""

from pathlib import Path
import argparse
from lib.config import STAGE_ROOT, LOG_ROOT
from lib.utils import get_timestamp, find_audio_files
from lib.soundfile import sha256, to_stage
from lib.tagging import touch_comment, set_tags
import sys


class Tee:
    def __init__(self, log_file):
        self.terminal = sys.stdout
        self.log = open(log_file, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


log_path = Path(LOG_ROOT) / f"stage-{get_timestamp()}.log"
sys.stdout = Tee(str(log_path))


def load_hashfile(hashfile_path):
    """
    Liest die Hashfile ein und gibt ein Dict[hash] = [filename1, filename2, ...]
    """
    hash_map = {}
    with open(hashfile_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) != 2:
                continue
            h, filename = parts
            if h not in hash_map:
                hash_map[h] = []
            hash_map[h].append(filename)
    return hash_map


def main():
    parser = argparse.ArgumentParser(
        description="Stage-Konverter (alle Audiodateien ins Stage-Format).")
    parser.add_argument('--use-hashfile', metavar="HASHFILE",
                        help="Vergleiche Hashes gegen diese Hashfile und nutze deren Endung für das Tagging.")
    args = parser.parse_args()

    timestamp = get_timestamp()
    stage_dir = Path(STAGE_ROOT) / timestamp
    stage_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Zielordner: {stage_dir}")

    src_root = Path('.').resolve()
    audiofiles = list(find_audio_files(src_root))
    print(f"[INFO] {len(audiofiles)} Audiodateien gefunden.")

    # Hashfile ggf. einlesen
    hash_map = {}
    if args.use_hashfile:
        hash_map = load_hashfile(args.use_hashfile)
        print(f"[INFO] Hashfile mit {len(hash_map)} Einträgen geladen.")

    errors = []
    processed = 0

    for rel_path in audiofiles:
        try:
            src_file = src_root / rel_path
            sha = sha256(src_file)
            out_file = stage_dir / (src_file.stem + ".flac")

            # -- Hashfile-Logik:
            gen0_format = src_file.suffix[1:].upper()
            taginfo = ""
            if hash_map:
                if sha in hash_map:
                    # Immer erste Endung für Tag, weitere ausgeben
                    first_match = hash_map[sha][0]
                    gen0_format = Path(first_match).suffix[1:].upper()
                    print(
                        f"[HASHFILE-TREFFER] {sha} → {first_match}")
                    if len(hash_map[sha]) > 1:
                        print(f"Weitere mögliche Namen für Hash:")
                        for alt in hash_map[sha][1:]:
                            print(f"  {alt}")
                else:
                    print(
                        f"[HASH NICHT IN HASHFILE] {sha} (verwende lokale Endung: {gen0_format})")

            # Transcodieren oder kopieren
            to_stage(str(src_file), str(out_file), flac_copy=True)

            # Kommentar-Tag korrigieren (falls nötig)
            touch_comment(str(out_file))

            # GEN0-Tags setzen
            set_tags(str(out_file), sha256=sha, gen0_format=gen0_format)

            print(f"[OK] {src_file} → {out_file}")
            print()

            processed += 1

        except Exception as e:
            print(f"[FEHLER] bei {rel_path}: {e}")
            errors.append((rel_path, str(e)))
            print(f"[ABBRUCH] Verarbeitung gestoppt nach {processed} Dateien.")
            if errors:
                print("\nFehlerübersicht:")
                for file, err in errors:
                    print(f"- {file}: {err}")
            return

    print(
        f"\nAlle {processed} Dateien wurden erfolgreich in {stage_dir} konvertiert – KEIN Fehler aufgetreten!")


if __name__ == "__main__":
    main()
