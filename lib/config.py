"""
lib/config.py

Zentrale Konfigurations- und Pfaddefinitionen für die DJ-Suite.

Diese Datei:
- Definiert PROJECT_ROOT als Basis für alle relativen Pfade
- Lädt die YAML-Konfiguration (djs-config.yaml)
- Stellt wichtige Verzeichnis- und Dateipfade bereit
- Definiert unterstützte Audioformate
- Enthält Hilfsfunktionen für Verzeichnisstruktur und Dateitypprüfungen
"""

import os
import yaml

# --- Projektbasis ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# --- YAML-Konfiguration einlesen ---
CONFIG_PATH = os.path.join(PROJECT_ROOT, "djs-config.yaml")


def _expand_path(path):
    """Hilfsfunktion zur Expansion von ~ im YAML"""
    return os.path.expanduser(path) if isinstance(path, str) and path.startswith("~") else path


with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# --- Allgemeine Konfigurationswerte aus YAML ---
LIBRARY_ROOT = _expand_path(cfg["library_root"])
DB_NAME = cfg.get("database_name", ".DB")
LOG_LEVEL = cfg.get("log_level", "INFO")
BAG_LUFS = float(cfg.get("bag_lufs", -21.0))

# --- Unterstützte/verarbeitete Audioformate ---
AUDIO_EXTENSIONS = [".wav", ".flac", ".mp3", ".aiff", ".aifc"]

# --- Erweiterte Liste für Suchfunktionen ---
EXTENDED_AUDIO_EXTENSIONS = sorted(set(
    AUDIO_EXTENSIONS + [
        '.aif', '.aac', '.alac', '.ogg', '.oga', '.opus',
        '.wma', '.wv', '.ape', '.m4a', '.mp4', '.mov',
        '.amr', '.ac3', '.dts', '.mka', '.spx', '.ra',
        '.au', '.snd', '.caf', '.tta', '.gsm'
    ]
))

# --- Abgeleitete Projektverzeichnisse ---
RAW_ROOT = os.path.join(LIBRARY_ROOT, "00 RAW")
ARCHIV_ROOT = os.path.join(LIBRARY_ROOT, "10 ARCHIV")
STAGE_ROOT = os.path.join(LIBRARY_ROOT, "20 STAGE")
WORKSPACE_ROOT = os.path.join(LIBRARY_ROOT, "30 WORKSPACE")
BAG_ROOT = os.path.join(LIBRARY_ROOT, "40 BAG")
LOG_ROOT = os.path.join(LIBRARY_ROOT, "98 LOG")
TEMP_ROOT = os.path.join(LIBRARY_ROOT, "99 TEMP")

ALL_ROOT_DIRS = [
    RAW_ROOT,
    ARCHIV_ROOT,
    STAGE_ROOT,
    WORKSPACE_ROOT,
    BAG_ROOT,
    LOG_ROOT,
    TEMP_ROOT,
]

# --- Pfade zu statischen Ressourcen ---
PICS_ROOT = os.path.join(PROJECT_ROOT, "lib", "pics")
EMPTY_COVER = os.path.join(PICS_ROOT, "empty.png")

# --- Hilfsfunktionen ---


def create_directory_structure():
    """
    Erstellt LIBRARY_ROOT und alle Projektverzeichnisse darunter.
    """
    os.makedirs(LIBRARY_ROOT, exist_ok=True)
    for path in ALL_ROOT_DIRS:
        os.makedirs(path, exist_ok=True)


def is_supported_audio_file(filename):
    """
    True, wenn die Datei eine für den Workflow unterstützte Erweiterung hat.
    """
    return any(filename.lower().endswith(ext) for ext in AUDIO_EXTENSIONS)


def is_known_audio_file(filename):
    """
    True, wenn die Datei eine bekannte, potenziell unterstützte Audio-/Multimedia-Erweiterung hat.
    """
    return any(filename.lower().endswith(ext) for ext in EXTENDED_AUDIO_EXTENSIONS)
