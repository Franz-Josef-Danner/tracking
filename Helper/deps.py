# Helper/deps.py
import sys, subprocess, importlib, os
from pathlib import Path

def ensure_vendor_path():
    base = Path(__file__).resolve().parent
    vendor = base / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    return vendor

def _pip(args):
    cmd = [sys.executable, "-m", "pip"] + args
    return subprocess.call(cmd)

def ensure_dependencies(*, upgrade_pip=False, upgrade_psutil=True):
    vendor = ensure_vendor_path()

    if upgrade_pip:
        _pip(["install", "--upgrade", "pip"])

    if upgrade_psutil:
        try:
            import psutil  # noqa: F401
        except Exception:
            rc = _pip(["install", "--upgrade", "--target", str(vendor), "psutil>=5.9"])
            importlib.invalidate_caches()
            if str(vendor) not in sys.path:
                sys.path.insert(0, str(vendor))
            if rc != 0:
                raise RuntimeError("psutil-Installation fehlgeschlagen")
        else:
            # Optional: dennoch in vendor spiegeln, wenn Systempaket unerwünscht
            pass
