# lib/config.py

import os
import yaml


def _expand_path(path):
    # --- Hilfsfunktion zur Expansion von ~ im YAML ---
    return os.path.expanduser(path) if isinstance(path, str) and path.startswith("~") else path


# --- YAML einlesen ---
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..',
    'djs-config.yaml'
)

CONFIG_PATH = os.path.abspath(CONFIG_PATH)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)


LIBRARY_ROOT = _expand_path(cfg["library_root"])
ARCHIV_ROOT = os.path.join(LIBRARY_ROOT, cfg["archiv_root"])
STAGE_ROOT = os.path.join(LIBRARY_ROOT, cfg["stage_root"])
WORKSPACE_ROOT = os.path.join(LIBRARY_ROOT, cfg["workspace_root"])
BAG_ROOT = os.path.join(LIBRARY_ROOT, cfg["bag_root"])
TEMP_ROOT = os.path.join(LIBRARY_ROOT, cfg.get("temp_root", "99 TEMP"))
LOG_ROOT = os.path.join(LIBRARY_ROOT, cfg.get("log_root", "98 LOG"))
DB_NAME = cfg.get("database_name", "DB")
LOG_LEVEL = cfg.get("log_level", "INFO")
AUDIO_EXTENSIONS = cfg["audio_extensions"]
