import os
import yaml
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "djs-config.yaml"


def check_config(cfg_path):
    print(f"\nPrüfe Konfiguration: {cfg_path}\n")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FEHLER: Konfigurationsdatei '{cfg_path}' nicht gefunden!")
        return
    except Exception as e:
        print(f"FEHLER beim Laden: {e}")
        return

    for key, value in cfg.items():
        print(f"{key}: {value}")

    print("\nPfad-Existenz-Checks:")
    for pfad_key in ["archiv_root", "stage_root", "engine_base"]:
        if pfad_key in cfg:
            resolved = os.path.expanduser(cfg[pfad_key])
            exists = os.path.isdir(resolved)
            print(
                f"  {pfad_key} (aufgelöst): {resolved}   [{'OK' if exists else 'FEHLT!'}]")


def main():
    parser = argparse.ArgumentParser(
        description="System-Checks für die DJ-Suite."
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Standard-Konfigurationsdatei (djs-config.yaml) prüfen"
    )
    # Hier kannst du später beliebig weitere Optionen ergänzen

    args = parser.parse_args()

    if args.config:
        check_config(DEFAULT_CONFIG)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
