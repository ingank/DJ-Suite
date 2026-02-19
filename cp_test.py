import chromaprint
print("chromaprint geladen aus:", getattr(chromaprint, "__file__", "?"))
print("Attribute:", [a for a in ("Fingerprinter","FingerprintError","decode_fingerprint") if hasattr(chromaprint,a)])
