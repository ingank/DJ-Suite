import subprocess, re, sys, numpy as np

def fp_ints_from_file(path: str) -> np.ndarray:
    """Ruft fpcalc -raw auf und gibt korrekt signierte int32-Array zurück."""
    try:
        res = subprocess.run(
            ["fpcalc", "-raw", path],
            capture_output=True, text=True, check=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        raise SystemExit("❌ 'fpcalc' nicht gefunden (Chromaprint-Tools installieren und PATH prüfen).")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"❌ fpcalc-Fehler:\n{e.stderr}")

    m = re.search(r"FINGERPRINT=([\d,\s-]+)", res.stdout)
    if not m:
        raise SystemExit("❌ Keine FINGERPRINT-Zeile gefunden.")
    # Zahlen einlesen und modulo 2^32 mappen → dann int32 interpretieren
    nums = [int(x) % (2**32) for x in m.group(1).split(",") if x.strip()]
    arr = np.array(nums, dtype=np.uint32).view(np.int32)
    return arr

def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    n = min(len(a), len(b))
    xor = np.bitwise_xor(a[:n], b[:n])
    return np.unpackbits(xor.view(np.uint8)).sum()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Verwendung: python cmpfp_rawfile.py track1.mp3 track2.mp3")
        sys.exit(1)

    A = fp_ints_from_file(sys.argv[1])
    B = fp_ints_from_file(sys.argv[2])
    if len(A) == 0 or len(B) == 0:
        raise SystemExit("❌ Leerer Fingerprint.")

    dist = hamming_distance(A, B)
    sim = 1 - dist / (min(len(A), len(B)) * 32)

    # Skala 0–1 mit 50 % Basislinie auf 0–100 % aufspannen
    sim_norm = max(0.0, (sim - 0.5) * 2)

    print(f"Hamming-Distanz: {dist}")
    print(f"Ähnlichkeit (roh): {sim*100:.2f}%")
    print(f"Ähnlichkeit (normiert 0–100): {sim_norm*100:.2f}%")
