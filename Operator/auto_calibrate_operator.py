# Operator/auto_calibrate_operator.py
from __future__ import annotations

import logging
import sys
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


def _run_track_operator_inprocess() -> None:
    """
    Führt den Track-Operator IM GLEICHEN Blender-Prozess aus (bpy vorhanden).
    Reihenfolge der Einstiegspunkte:
      1) Operator.track_operator.main()    -> nutzt Rückgabecode
      2) Operator.track_operator.run()     -> fire-and-forget
      3) bpy.ops.kaiserlich_tracker.track  -> falls als Blender-Operator registriert
    """
    LOGGER.info("Starte Track-Operator (in-process)…")
    try:
        from Operator import track_operator  # lazy import vermeidet Zyklen

        # 1) main()
        entry = getattr(track_operator, "main", None)
        if callable(entry):
            rc = entry()
            if isinstance(rc, int) and rc != 0:
                raise RuntimeError(f"track_operator.main() exited with code {rc}")
            LOGGER.info("Track-Operator via main() abgeschlossen.")
            return

        # 2) run()
        entry = getattr(track_operator, "run", None)
        if callable(entry):
            entry()
            LOGGER.info("Track-Operator via run() abgeschlossen.")
            return

        # 3) Blender-Operator als Fallback
        LOGGER.info("Kein main()/run() gefunden – versuche Blender-Operator 'kaiserlich_tracker.track' …")
        try:
            result = bpy.ops.kaiserlich_tracker.track('EXEC_DEFAULT')
            LOGGER.info("Track-Operator (bpy.ops) Result: %s", result)
            return
        except AttributeError:
            raise RuntimeError(
                "Weder main()/run() in Operator.track_operator noch Blender-Operator 'kaiserlich_tracker.track' vorhanden."
            )

    except Exception as exc:
        LOGGER.exception("Track-Operator (in-process) schlug fehl: %s", exc)
        raise


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

            # Direkt im Anschluss: Detect-Adapt (ohne UI)
            _run_detect_adapt_operator()

            # Danach: Tracking im selben Prozess (bpy verfügbar)
            _run_track_operator_inprocess()

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
