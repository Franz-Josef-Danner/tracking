# tracking-efficent/Helper/deps.py
import sys, subprocess, importlib, os
from pathlib import Path

def _pip(args):
    # Vermeidet den Versionshinweis und reduziert Rauschen
    base = [sys.executable, "-m", "pip"]
    return subprocess.call(base + args + ["--disable-pip-version-check"])

def ensure_vendor_path():
    vendor = Path(__file__).resolve().parent / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    vp = str(vendor)
    if vp not in sys.path:
        sys.path.insert(0, vp)
    return vp

def ensure_dependencies(*, upgrade_pip=True, upgrade_psutil=True):
    vendor = ensure_vendor_path()

    if upgrade_pip:
        # pip selbst upgraden (global in der eingebetteten Blender-Python)
        _pip(["install", "--upgrade", "pip", "-q"])

    if upgrade_psutil:
        # Immer gegen PyPI prüfen und neueste nehmen
        rc = _pip(["install", "--upgrade", "--upgrade-strategy", "eager",
                   "--no-cache-dir", "--target", vendor, "psutil"])
        importlib.invalidate_caches()
        # psutil laden (nun aus vendor)
        import psutil  # noqa: F401
