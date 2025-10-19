# Operator/auto_calibrate_operator.py
from __future__ import annotations

import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import Any

# Blender-API
try:
    import bpy
except Exception as exc:  # pragma: no cover
    raise RuntimeError("Dieses Modul muss innerhalb von Blender ausgeführt werden.") from exc


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOGGER = logging.getLogger("Operator.auto_calibrate")
if not LOGGER.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _f = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_f)
    LOGGER.addHandler(_h)
LOGGER.setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _addon_root() -> Path:
    """
    Liefert das Add-on-Wurzelverzeichnis, also den Ordner, der 'Operator/' enthält.
    Erwartete Struktur: <addon_root>/Operator/auto_calibrate_operator.py
    """
    here = Path(__file__).resolve()
    operator_dir = here.parent  # .../Operator
    addon_root = operator_dir.parent  # .../tracking-KI (oder Add-on-Root)
    return addon_root


def _set_scene_prop(scene: Any, prop: str, value: float) -> None:
    """Setzt eine Scene-Property defensiv, loggt hart bei Nichtverfügbarkeit."""
    if hasattr(scene, prop):
        try:
            setattr(scene, prop, value)
            LOGGER.info("Set '%s' -> %s", prop, value)
        except Exception as exc:
            LOGGER.error("Konnte Property '%s' nicht setzen: %s", prop, exc)
            raise
    else:
        LOGGER.warning("Property '%s' nicht gefunden – UI/Property-Registrierung prüfen.", prop)


def _run_detect_adapt_operator() -> None:
    """
    Startet den Detect-Adapt-Operator ohne Zusatzdialog.
    Erwartete bl_idname-Konvention: 'kaiserlich_tracker.detect_adapt'
    """
    LOGGER.info("Starte Detect-Adapt-Operator…")
    try:
        result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
        LOGGER.info("Detect-Adapt Result: %s", result)
    except AttributeError:
        LOGGER.error(
            "Operator 'kaiserlich_tracker.detect_adapt' nicht gefunden. "
            "Bitte bl_idname und Registrierung in Operator/detect_adapt_operator.py prüfen."
        )
        raise
    except Exception as exc:
        LOGGER.exception("Detect-Adapt-Operator schlug fehl: %s", exc)
        raise


def _launch_track_operator_subprocess() -> None:
    """
    Triggert anschließend Operator/track_operator.py als separaten Prozess.
    Fix: Setzt PYTHONPATH dynamisch auf das Add-on-Root, damit 'Operator' importierbar ist.
    """
    addon_root = _addon_root()
    operator_pkg = addon_root / "Operator"
    track_file = operator_pkg / "track_operator.py"

    if not track_file.exists():
        raise FileNotFoundError(
            f"track_operator.py nicht gefunden unter: {track_file}"
        )

    # Python/Blender-Umgebung aufsetzen
    env = os.environ.copy()

    # Sicherstellen, dass das Add-on-Root (Elternordner von 'Operator') im PYTHONPATH ist.
    # Damit funktioniert: `python -m Operator.track_operator`
    current_pp = env.get("PYTHONPATH", "")
    new_pp = str(addon_root)
    if current_pp:
        # OS-separierter Suchpfad (Windows: ';', Posix: ':')
        new_pp = new_pp + os.pathsep + current_pp
    env["PYTHONPATH"] = new_pp

    LOGGER.info("Starte Track-Operator (Subprozess)…")
    LOGGER.info("PYTHONPATH ergänzt um: %s", addon_root)

    cmd = [sys.executable, "-m", "Operator.track_operator"]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,  # <— entscheidend
    )
    out, err = proc.communicate()

    if out:
        for line in out.strip().splitlines():
            LOGGER.info("track_operator: %s", line)
    if err:
        for line in err.strip().splitlines():
            LOGGER.warning("track_operator[stderr]: %s", line)

    if proc.returncode != 0:
        raise RuntimeError(f"track_operator exited with code {proc.returncode}")

    LOGGER.info("Track-Operator erfolgreich beendet.")


# -----------------------------------------------------------------------------
# Blender Operator
# -----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und führt danach Detect-Adapt und Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        try:
            scene = context.scene

            # --- Rotation Thresholds ---
            _set_scene_prop(scene, "kaiserlich_rot_thresh_x", 1.0)
            _set_scene_prop(scene, "kaiserlich_rot_thresh_y", 1.0)

            # --- Scale Thresholds ---
            _set_scene_prop(scene, "kaiserlich_scale_thresh_min", 1.0)
            _set_scene_prop(scene, "kaiserlich_scale_thresh_max", 1.0)

            # --- LocRotScale Thresholds ---
            _set_scene_prop(scene, "kaiserlich_rot_scale_thresh_rot", 1.0)
            _set_scene_prop(scene, "kaiserlich_rot_scale_thresh_scale", 1.0)

            # --- Perspective Thresholds ---
            _set_scene_prop(scene, "kaiserlich_perspective_thresh", 1.0)

            # Direkt im Anschluss: Detect-Adapt fahren (ohne UI)
            _run_detect_adapt_operator()

            # Danach: Tracking-Operator als separaten Prozess (mit korrekt gesetztem PYTHONPATH)
            _launch_track_operator_subprocess()

            return {"FINISHED"}

        except Exception as exc:
            self.report({'ERROR'}, f"Auto-Calibrate/Detect-Adapt/Track fehlgeschlagen: {exc}")
            return {"CANCELLED"}


# -----------------------------------------------------------------------------
# Blender Registration
# -----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":  # pragma: no cover
    try:
        unregister()
    except Exception:
        pass
    register()
