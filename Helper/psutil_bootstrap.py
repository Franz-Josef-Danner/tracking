# Helper/psutil_bootstrap.py
import os, sys, subprocess, importlib

def ensure_psutil(auto_install=False, target_dir=None, logger=print):
    """
    Prüft, ob psutil importierbar ist. Optional installiert es psutil:
      - per pip in ein Add-on-lokales 'vendor'-Verzeichnis,
      - fügt dieses Verzeichnis dem sys.path hinzu,
      - invalidiert Caches und importiert psutil.
    Rückgabe: (ok: bool, psutil_or_none, msg: str)
    """
    try:
        import psutil  # bereits vorhanden
        return True, psutil, "psutil bereits vorhanden"
    except Exception:
        if not auto_install:
            return False, None, "psutil nicht vorhanden"

    # --- Installation starten ---
    # pip bereitstellen (falls nötig)
    try:
        import ensurepip  # noqa: F401
        ensurepip.bootstrap()
    except Exception as e:
        return False, None, f"ensurepip fehlgeschlagen: {e}"

    # Zielordner
    if target_dir is None:
        target_dir = os.path.join(os.path.dirname(__file__), "vendor")
    os.makedirs(target_dir, exist_ok=True)

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "psutil", "--target", target_dir]
    logger(f"🔧 Installiere psutil nach: {target_dir}\n$ {' '.join(cmd)}")
    try:
        rc = subprocess.call(cmd)
        if rc != 0:
            return False, None, f"pip rc={rc}"
    except Exception as e:
        return False, None, f"pip-Call fehlgeschlagen: {e}"

    if target_dir not in sys.path:
        sys.path.insert(0, target_dir)
    importlib.invalidate_caches()

    try:
        import psutil  # noqa: F401
        return True, psutil, "psutil installiert"
    except Exception as e:
        return False, None, f"Import nach Installation fehlgeschlagen: {e}"
