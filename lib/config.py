"""
lib/config.py

Zentrale Konfigurations- und Pfaddefinitionen für die DJ-Suite.

Diese Datei:
- Definiert PROJECT_ROOT als Basis für alle relativen Pfade
- Lädt die YAML-Konfiguration (djs-config.yaml)
- Stellt wichtige Verzeichnis- und Dateipfade bereit
- Definiert unterstützte Audioformate
- Enthält Hilfsfunktionen für Verzeichnisstruktur
"""

import os
import sys
import shutil
import yaml

# --- Externe Abhängigkeiten: HARTE Prüfung beim Import ---
_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None
if not (_HAS_FFMPEG and _HAS_FFPROBE):
    missing = []
    if not _HAS_FFMPEG:
        missing.append("ffmpeg")
    if not _HAS_FFPROBE:
        missing.append("ffprobe")
    sys.stderr.write(f"Fehlende Abhängigkeiten: {', '.join(missing)}\n")
    raise RuntimeError(
        "Kritische Abhängigkeiten fehlen – bitte installieren und im PATH verfügbar machen.")

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

# --- Audio-Formate ---
# Primäre/verarbeitete Audioformate im Workflow:
PRIMARY_AUDIO_EXTENSIONS = [".mp3", ".flac", ".wav", ".aiff", ".aifc"]

# Bekannte Audio-/Multimedia-Formate (enger kuratiert):
KNOWN_LOSSY_AUDIO_EXTENSIONS = {
    ".aac", ".ac3", ".amr", ".dts", ".eac3", ".g722", ".g726", ".gsm",
    ".mp2", ".mp3", ".mpa", ".mpc", ".opus", ".qcp", ".voc", ".wma"
}

KNOWN_LOSSLESS_AUDIO_EXTENSIONS = {
    ".aif", ".aiff", ".alac", ".ape", ".flac", ".mlp", ".thd", ".tak",
    ".tta", ".wav", ".w64", ".aifc"
}

# Gesamtliste aller bekannten Audio-Formate, alphabetisch sortiert
KNOWN_AUDIO_EXTENSIONS = sorted(
    KNOWN_LOSSY_AUDIO_EXTENSIONS | KNOWN_LOSSLESS_AUDIO_EXTENSIONS
)


# Rückwärtskompatible Alias-Namen (damit bestehender Code weiter läuft)
AUDIO_EXTENSIONS = PRIMARY_AUDIO_EXTENSIONS
EXTENDED_AUDIO_EXTENSIONS = KNOWN_AUDIO_EXTENSIONS

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
