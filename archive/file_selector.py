# lib/file_selector.py

import os
import string
import msvcrt

PAGE_SIZE = 26  # A-Z


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_key():
    key = msvcrt.getch()
    if key == b'\r':
        return 'ENTER'
    elif key == b'\xe0':
        sub = msvcrt.getch()
        if sub == b'M':
            return 'RIGHT'
        elif sub == b'K':
            return 'LEFT'
        elif sub == b'H':
            return 'UP'
        elif sub == b'P':
            return 'DOWN'
        else:
            return ''
    return key.decode('utf-8').upper()


def paginate_files(files):
    return [files[i:i + PAGE_SIZE] for i in range(0, len(files), PAGE_SIZE)]


def choose_file_from_folder(folder=".", extensions=(".flac",)):
    files = [f for f in os.listdir(folder) if f.lower().endswith(extensions)]
    files.sort()
    if not files:
        print("Keine FLAC-Dateien im aktuellen Ordner gefunden.")
        return None

    pages = paginate_files(files)
    current_page = 0

    while True:
        clear_screen()
        page_files = pages[current_page]

        print(f"Dateiauswahl – Seite {current_page + 1}/{len(pages)}")
        print("\nWähle mit A-Z, ←/→ zum Blättern, ENTER zum Abbrechen\n")

        for idx, filename in enumerate(page_files):
            letter = string.ascii_uppercase[idx]
            print(f"  {letter}: {filename}")

        key = get_key()

        if key == 'ENTER':
            return None
        elif key == 'RIGHT' and current_page < len(pages) - 1:
            current_page += 1
        elif key == 'LEFT' and current_page > 0:
            current_page -= 1
        elif key in string.ascii_uppercase:
            index = string.ascii_uppercase.index(key)
            if index < len(page_files):
                return os.path.join(folder, page_files[index])


def get_file_from_input_or_menu(argv=None):
    if argv and len(argv) > 1 and os.path.isfile(argv[1]):
        return argv[1]
    return choose_file_from_folder()


# Beispielverwendung in dj-tagger.py:
# from lib.file_selector import get_file_from_input_or_menu
# filepath = get_file_from_input_or_menu(sys.argv)
