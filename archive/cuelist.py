"""
cuelist.py

Konvertiert Audacity Marker-TXT-Dateien in standardkonforme .cue-Dateien.
Nur exakt drei Tab-getrennte Felder pro Zeile (Startzeit, Endzeit, Label) werden akzeptiert.
.cue-Ausgabe in latin-1/ANSI-Kodierung.

(c) 2024 – Public Domain
"""

import argparse
import os
import sys

SUPPORTED_FORMATS = {
    '.wav': 'WAVE',
    '.flac': 'FLAC',
    '.mp3': 'MP3'
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Konvertiert eine Audacity Marker-TXT-Datei in eine CUE-Datei. "
            "Die Eingabedatei muss aus exakt drei Tab-getrennten Feldern pro Zeile bestehen "
            "(Startzeit, Endzeit, Label; Label darf leer sein). "
            "Labels, Performer und Albumtitel dürfen nur Zeichen enthalten, "
            "die im klassischen .cue-Format (latin-1/ANSI) erlaubt sind!"
        ),
        epilog=(
            "Beispiel:\n"
            "  python marker2cue.py input.txt album.flac -o album.cue -p \"Künstler\" -t \"Albumtitel\"\n"
            "Nur .mp3, .wav oder .flac sind als Audiodatei zulässig."
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('infile', help='Audacity Marker-TXT-Datei (Input)')
    parser.add_argument(
        'audiofile', help='Audiodatei (für FILE-Zeile, z.B. album.flac)')
    parser.add_argument('-o', '--outfile', help='Name der Ausgabedatei (.cue)')
    parser.add_argument('-p', '--performer',
                        help='Performer (Künstlername, optional)')
    parser.add_argument('-t', '--title', help='Albumtitel (optional)')
    parser.add_argument('--trackstart', type=int, default=1,
                        help='Erste Tracknummer (Standard: 1)')
    return parser.parse_args()


def error_exit(msg):
    print(f"Fehler: {msg}", file=sys.stderr)
    sys.exit(1)


def validate_audio_filename(audiofile):
    ext = os.path.splitext(audiofile)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        error_exit(
            f"Audiodatei '{audiofile}' hat kein unterstütztes Format. "
            f"Zulässig sind nur: .mp3, .wav, .flac"
        )
    return SUPPORTED_FORMATS[ext]


def check_latin1_compatibility(s, context):
    try:
        s.encode('latin-1')
    except UnicodeEncodeError as e:
        offending_char = s[e.start:e.end]
        error_exit(
            f"Das Zeichen '{offending_char}' aus {context} kann nicht im Zeichensatz Latin-1/ANSI dargestellt werden.\n"
            f"Bitte verwenden Sie nur Zeichen, die im klassischen .cue-Format (Latin-1/ANSI) zulässig sind."
        )


def validate_labels_for_encoding(labels, performer, albumtitle):
    if performer:
        check_latin1_compatibility(performer, f"Performer '{performer}'")
    if albumtitle:
        check_latin1_compatibility(albumtitle, f"Albumtitel '{albumtitle}'")
    for idx, label in enumerate(labels, 1):
        check_latin1_compatibility(label, f"Label '{label}' (Track {idx})")


def validate_input_file(input_path):
    lines = []
    with open(input_path, encoding='utf-8') as f:
        for i, raw_line in enumerate(f, 1):
            line = raw_line.rstrip('\n\r')
            parts = line.split('\t')
            if len(parts) != 3:
                error_exit(
                    f"Zeile {i}: Falsches Format! "
                    "Erwartet werden drei Tab-getrennte Felder: Startzeit<TAB>Endzeit<TAB>Label "
                    "(Label darf leer sein). Prüfen Sie Ihre Eingabedatei!"
                )
            # Prüfe Startzeit
            try:
                start_time = float(parts[0].replace(',', '.'))
            except ValueError:
                error_exit(
                    f"Zeile {i}: Startzeit ist ungültig oder fehlt ('{parts[0]}').")
            # Endzeit (wird ignoriert, kann aber geprüft werden)
            try:
                _ = float(parts[1].replace(',', '.'))
            except ValueError:
                error_exit(
                    f"Zeile {i}: Endzeit ist ungültig oder fehlt ('{parts[1]}').")
            label = parts[2].strip()
            lines.append((start_time, label, i))
    if not lines:
        error_exit("Keine Marker in der Eingabedatei gefunden.")
    return lines


def seconds_to_cue_time(seconds):
    if seconds < 0:
        error_exit("Negative Startzeit erkannt.")
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    frames = int(round((seconds - int(seconds)) * 75))
    if frames >= 75:
        sec += frames // 75
        frames = frames % 75
    if sec >= 60:
        minutes += sec // 60
        sec = sec % 60
    return f"{minutes:02d}:{sec:02d}:{frames:02d}"


def build_cue_content(
    marker_lines, audiofile, audioformat, performer, albumtitle, trackstart
):
    out = []
    out.append(f'FILE "{audiofile}" {audioformat}')
    if performer:
        out.append(f'PERFORMER "{performer}"')
    if albumtitle:
        out.append(f'TITLE "{albumtitle}"')
    for idx, (start_time, label, _) in enumerate(marker_lines, trackstart):
        track_label = label if label else f"Titel {idx}"
        out.append(f'  TRACK {idx:02d} AUDIO')
        out.append(f'    TITLE "{track_label}"')
        out.append(f'    INDEX 01 {seconds_to_cue_time(start_time)}')
    return '\n'.join(out) + '\n'


def write_cue_file(outfile, cue_content):
    if os.path.exists(outfile):
        error_exit(
            f"Die Ausgabedatei '{outfile}' existiert bereits. Bitte löschen oder einen anderen Namen wählen.")
    try:
        with open(outfile, 'w', encoding='latin-1') as f:
            f.write(cue_content)
    except Exception as e:
        error_exit(f"Fehler beim Schreiben der .cue-Datei: {e}")


def main():
    args = parse_args()
    outfile = args.outfile
    if not outfile:
        basename = os.path.splitext(os.path.basename(args.infile))[0]
        outfile = basename + '.cue'
    audioformat = validate_audio_filename(args.audiofile)
    marker_lines = validate_input_file(args.infile)
    all_labels = [
        label if label else f"Titel {i+args.trackstart}" for i, (_, label, _) in enumerate(marker_lines)]
    validate_labels_for_encoding(
        all_labels, args.performer or '', args.title or '')
    cue_content = build_cue_content(
        marker_lines, args.audiofile, audioformat,
        args.performer or '', args.title or '', args.trackstart
    )
    write_cue_file(outfile, cue_content)
    print(
        f"Erfolgreich {len(marker_lines)} Tracks in '{outfile}' geschrieben.")


if __name__ == "__main__":
    main()
