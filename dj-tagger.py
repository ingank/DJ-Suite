import os
import sys
from lib.file_selector import choose_file_from_folder
from lib.tagging import set_tags
import msvcrt
import string

# ----------------------------------------
# Konfiguration der Tag-Listen
# ----------------------------------------
ENERGY_LEVELS = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
MOOD_TAGS = {"A": "ambient", "B": "dreamy", "C": "melancholic", "D": "nostalgic", "E": "romantic",
             "F": "calm", "G": "chill", "H": "groovy", "I": "uplifting", "J": "happy", "K": "tense", "L": "aggressive"}
TECH_TAGS = {"A": "retro", "B": "oldschool", "C": "lofi",
             "D": "analog", "E": "digital", "F": "raw"}
SET_TAGS = {"A": "intro", "B": "mixin", "C": "mixout",
            "D": "loop", "E": "peak", "F": "transition"}

PAGE_ORDER = ["mood", "tech", "set"]

# ----------------------------------------


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_key():
    key = msvcrt.getch()
    if key == b'\r':
        return "ENTER"
    elif key == b'\xe0':
        subkey = msvcrt.getch()
        if subkey == b'M':
            return "RIGHT"
        if subkey == b'K':
            return "LEFT"
        if subkey == b'H':
            return "UP"
        if subkey == b'P':
            return "DOWN"
        if subkey == b'S':
            return "ESC"
    return key.decode("utf-8").upper()


def toggle_tag(tagset, tag):
    if tag in tagset:
        tagset.remove(tag)
    else:
        tagset.add(tag)
    return tagset


def build_comment_code(energy, moods, techs, sets):
    mood_part = "-".join(sorted(moods)) if moods else ""
    tech_part = "-".join(sorted(techs)) if techs else ""
    set_part = "-".join(sorted(sets)) if sets else ""
    return f"[{energy}] {mood_part} ; {tech_part} ; {set_part}"


def render_page(page, energy, moods, techs, sets):
    clear_screen()
    print(f"Seite {PAGE_ORDER.index(page)+1}/3 – {page.title()}-Tags")

    if page == "mood":
        print("Mood-Auswahl (A–L), Energie (1–6), → = weiter, ENTER = speichern")
        print(f"Energielevel: [{energy}]\n")
        tags = MOOD_TAGS
        selected = moods
    elif page == "tech":
        print("Tech-Tags (A–F), ←/→ blättern, ENTER = speichern\n")
        tags = TECH_TAGS
        selected = techs
    else:
        print("Set-Tags (A–F), ←/→ blättern, ENTER = speichern\n")
        tags = SET_TAGS
        selected = sets

    for key, tag in tags.items():
        mark = "[x]" if tag in selected else "[ ]"
        print(f"  {key}: {tag:<12} {mark}")

    print("\n------------------------------------------")
    print("Aktueller DJ-TAG:")
    print(build_comment_code(energy, moods, techs, sets))
    print("------------------------------------------")


def tagging_ui(filepath):
    energy = 3
    moods, techs, sets = set(), set(), set()
    page = "mood"

    while True:
        render_page(page, energy, moods, techs, sets)
        key = get_key()

        if key == "ENTER":
            break
        elif key == "RIGHT":
            page = PAGE_ORDER[(PAGE_ORDER.index(page) + 1) % len(PAGE_ORDER)]
        elif key == "LEFT":
            page = PAGE_ORDER[(PAGE_ORDER.index(page) - 1) % len(PAGE_ORDER)]
        elif page == "mood":
            if key in ENERGY_LEVELS:
                energy = ENERGY_LEVELS[key]
            elif key in MOOD_TAGS:
                moods = toggle_tag(moods, MOOD_TAGS[key])
        elif page == "tech" and key in TECH_TAGS:
            techs = toggle_tag(techs, TECH_TAGS[key])
        elif page == "set" and key in SET_TAGS:
            sets = toggle_tag(sets, SET_TAGS[key])

    return build_comment_code(energy, moods, techs, sets)


def write_tag_to_file(filepath, dj_code):
    set_tags(filepath, {"DJ-TAG": dj_code})
    print(f"\n✅ DJ-TAG gespeichert in: {os.path.basename(filepath)}")


def tag_multiple_tracks():
    folder = os.getcwd()
    files = [f for f in os.listdir(folder) if f.lower().endswith(".flac")]
    files.sort()

    if not files:
        print("Keine FLAC-Dateien im aktuellen Ordner gefunden.")
        return

    index = 0
    while 0 <= index < len(files):
        filepath = os.path.join(folder, files[index])
        clear_screen()
        print(f"Track {index + 1}/{len(files)}: {os.path.basename(filepath)}\n")

        dj_code = tagging_ui(filepath)
        print("\nFinaler DJ-TAG:")
        print(dj_code)

        print("\nIn Datei schreiben? (J/N): ", end="")
        confirm = input().strip().lower()
        if confirm == "j":
            write_tag_to_file(filepath, dj_code)
        else:
            print("⏭ Übersprungen.")

        print("\nWeiter mit ↑ / ↓, ← = Auswahlmenü, ESC = Ende")
        while True:
            nav = get_key()
            if nav == "UP":
                index -= 1
                break
            elif nav == "DOWN":
                index += 1
                break
            elif nav == "LEFT":
                return tag_multiple_tracks()
            elif nav == "ESC":
                return


if __name__ == "__main__":
    tag_multiple_tracks()
