# -*- coding: utf-8 -*-
"""
Operator/auto_calibrate_operator.py

Blender Operator:
- Name: KAISERLICHTRACKER_OT_auto_calibrate
- bl_idname: "kaiserlich_tracker.auto_calibrate"
- Zweck: Auto-Kalibrierung durchführen und danach detect_adapt_operator starten.

Voraussetzungen:
- Liegt im selben Paket/Ordner wie detect_adapt_operator.py (Operator/).
- Wenn detect_adapt als Blender-Operator existiert (z.B. "kaiserlich_tracker.detect_adapt"),
  wird er direkt via bpy.ops.* getriggert.
- Fallbacks: Import + main(), runpy, subprocess.
"""

from __future__ import annotations

import bpy  # type: ignore
import json
import logging
import pathlib
import runpy
import sys
import time
import traceback
import typing as _t
import subprocess
import importlib


# -----------------------------
# Konstante(n) / Defaults
# -----------------------------

ADDON_NAME = "KAISERLICHTRACKER"
LOGGER_NAME = f"{ADDON_NAME}/AutoCalibrate"
LOG = logging.getLogger(LOGGER_NAME)

# Optional: Schalte Standard-Logging an, falls nicht global konfiguriert
if not LOG.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# -----------------------------
# Hilfsfunktionen (Kalibrierung)
# -----------------------------

def _load_input_from_scene() -> dict:
    """
    Beispielhafte Datenquelle aus der aktuellen Scene.
    Ersetze/Erweitere nach Bedarf durch echte Daten (Objekte, CustomProps, etc.).
    """
    scene = bpy.context.scene
    # Placeholder: ersetze durch reale Parameterquellen
    payload = {
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "score": 1.0,  # Dummy-Startwert
    }
    return payload


def _persist_results_to_textblock(name: str, data: dict) -> None:
    """
    Persistiert Ergebnisse in einen Blender Text-Block (bequem für Debug/QA).
    Alternativ: schreibe auf Disk in den Projektpfad.
    """
    txt = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    txt.clear()
    txt.write(json.dumps(data, indent=2, ensure_ascii=False))


def _dummy_adjust(data: dict, step: int) -> dict:
    """
    Platzhalter-Kalibrierung: dämpft einen Score.
    Ersetze durch echte Kalibrierlogik.
    """
    score = float(data.get("score", 1.0))
    score *= 0.7  # fiktive Konvergenz
    return {**data, "score": round(score, 6), "step": step}


def _dummy_check_convergence(data: dict, threshold: float = 0.01) -> bool:
    score = float(data.get("score", 1.0))
    return score < threshold


# -----------------------------
# Detect/Adapt Launcher (robust)
# -----------------------------

def _launch_detect_adapt(self_report: _t.Callable[[str, set], None] | None = None) -> None:
    """
    Startet detect_adapt_operator mit Prioritäten:
      1) Blender-Operator: bpy.ops.kaiserlich_tracker.detect_adapt()
      2) Python-Import: Operator.detect_adapt_operator:main()
      3) runpy: detect_adapt_operator.py als __main__
      4) subprocess: python detect_adapt_operator.py

    Exceptions werden erst im letzten Schritt durchgereicht.
    """

    def _report(level: str, msg: str) -> None:
        LOG.log(getattr(logging, level, logging.INFO), msg)
        if self_report:
            try:
                self_report(msg, {"INFO"} if level == "INFO" else {"WARNING"})
            except Exception:
                pass

    # 1) Bevorzugt: Blender-Operator (falls registriert)
    try:
        # Prüfe dynamisch, ob die op factory existiert
        ops_ns = getattr(bpy.ops, "kaiserlich_tracker", None)
        if ops_ns and hasattr(ops_ns, "detect_adapt"):
            _report("INFO", "Starte detect_adapt via bpy.ops.kaiserlich_tracker.detect_adapt()")
            res = bpy.ops.kaiserlich_tracker.detect_adapt("INVOKE_DEFAULT")
            _report("INFO", f"detect_adapt Operator Result: {res!r}")
            return
    except Exception:
        LOG.debug("Blender-Operator-Fallback nicht verfügbar:\n%s", traceback.format_exc())

    # 2) Import + main()
    try:
        _report("INFO", "Starte detect_adapt via Python-Import (Operator.detect_adapt_operator)")
        mod = importlib.import_module("Operator.detect_adapt_operator")
        if hasattr(mod, "main") and callable(mod.main):
            mod.main()  # type: ignore[attr-defined]
            return
    except Exception:
        LOG.debug("Import-Fallback fehlgeschlagen:\n%s", traceback.format_exc())

    # 3) runpy
    try:
        here = pathlib.Path(__file__).resolve()
        script_path = here.with_name("detect_adapt_operator.py")
        if script_path.exists():
            _report("INFO", f"Starte detect_adapt via runpy: {script_path}")
            runpy.run_path(str(script_path), run_name="__main__")
            return
    except Exception:
        LOG.debug("runpy-Fallback fehlgeschlagen:\n%s", traceback.format_exc())

    # 4) subprocess
    here = pathlib.Path(__file__).resolve()
    script_path = here.with_name("detect_adapt_operator.py")
    _report("INFO", f"Starte detect_adapt via Subprozess: {script_path}")
    subprocess.check_call([sys.executable, str(script_path)])


# -----------------------------
# Blender Operator
# -----------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und testet danach jeden Parameter isoliert."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    # Optionale UI-Properties (sichtbar im Operator-Panel)
    max_iters: bpy.props.IntProperty(  # type: ignore
        name="Max Iters",
        description="Maximale Iterationen der Auto-Kalibrierung",
        default=5,
        min=1,
        soft_max=50,
    )
    timeout_s: bpy.props.IntProperty(  # type: ignore
        name="Timeout (s)",
        description="Zeitlimit in Sekunden",
        default=300,
        min=1,
        soft_max=3600,
    )
    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose",
        description="Detailliertes Logging aktivieren",
        default=False,
    )

    def execute(self, context: bpy.types.Context):  # noqa: D401
        """
        Führt die Auto-Kalibrierung synchron aus und startet anschließend detect_adapt.
        """
        t0 = time.perf_counter()
        try:
            if self.verbose:
                LOG.setLevel(logging.DEBUG)
            LOG.info("Auto-Kalibrierung gestartet (iters=%d, timeout=%ds)", self.max_iters, self.timeout_s)

            # --- Input laden (ersetzbar durch echte Datenquellen) ---
            data = _load_input_from_scene()

            # --- Iterationsschleife ---
            adjusted = dict(data)
            for it in range(1, int(self.max_iters) + 1):
                adjusted = _dummy_adjust(adjusted, step=it)
                if _dummy_check_convergence(adjusted):
                    LOG.debug("Konvergenz erreicht in Iteration %d", it)
                    break

                if (time.perf_counter() - t0) > float(self.timeout_s):
                    LOG.warning("Timeout erreicht (%ss), vorzeitiger Abbruch.", self.timeout_s)
                    break

            # --- Persistenz (Blender Text-Block; alternativ: Datei) ---
            result_payload = {
                "data": adjusted,
                "metrics": {
                    "iters": it,
                    "converged": _dummy_check_convergence(adjusted),
                    "duration_s": round(time.perf_counter() - t0, 3),
                },
                "version": "1.0.0",
            }
            _persist_results_to_textblock(f"{ADDON_NAME}_auto_calibrate.json", result_payload)

            # User-Feedback
            self.report({"INFO"}, f"{ADDON_NAME}: Auto-Calib abgeschlossen (iters={it})")

        except Exception as ex:
            LOG.error("Auto-Kalibrierung fehlgeschlagen: %s", ex)
            LOG.debug("Traceback:\n%s", traceback.format_exc())
            self.report({"ERROR"}, f"{ADDON_NAME}: Auto-Calib Fehler – {ex}")
            return {'CANCELLED'}

        # --- Detect/Adapt starten (robust) ---
        try:
            _launch_detect_adapt(self_report=self.report)
        except subprocess.CalledProcessError as cpe:
            self.report({"ERROR"}, f"{ADDON_NAME}: detect_adapt Subprozess-Fehler (rc={cpe.returncode})")
            return {'CANCELLED'}
        except Exception as ex:
            LOG.error("detect_adapt fehlgeschlagen: %s", ex)
            LOG.debug("Traceback:\n%s", traceback.format_exc())
            self.report({"ERROR"}, f"{ADDON_NAME}: detect_adapt Fehler – {ex}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context: bpy.types.Context, event: _t.Any):
        # Optionales Invoke-Verhalten: sofort ausführen (keine Popup-Dialoge)
        return self.execute(context)


# -----------------------------
# Blender Registration
# -----------------------------

_CLASSES = (
    KAISERLICHTRACKER_OT_auto_calibrate,
)

def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    LOG.info("%s: auto_calibrate Operator registriert.", ADDON_NAME)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    LOG.info("%s: auto_calibrate Operator deregistriert.", ADDON_NAME)


# Für Standalone-Tests im Blender-Python-Interpreter:
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
