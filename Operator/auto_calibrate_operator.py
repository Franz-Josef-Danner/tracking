import bpy
from typing import List, Dict, Any, Optional
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.reset_helper import reset_all_thresholds, THRESH_LIST, set_scene_value, get_scene_value

# Direct import of the procedural tracking function used by the operator
from ..Operator.track_operator import track_cycle as run_track_cycle


# ------------------------------------------------------------
# Utility: Differenz neuer Marker
# ------------------------------------------------------------
def get_new_markers(context, before_snapshot: List[Dict[str, Any]]) -> List[str]:
    before_names = {m['track'] for m in before_snapshot}
    after = snapshot_active_markers(context)
    after_names = {m['track'] for m in after}
    return list(after_names - before_names)


# ------------------------------------------------------------
# Tracking-Zyklus mit Snapshot und Bereinigung
# ------------------------------------------------------------
def run_tracking_cycle(context) -> int:
    start = get_start_frame(context)
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return 0

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return 0

    # Snapshot vor Detect
    old_markers = snapshot_active_markers(context)

    # Detect (falls Operator registriert)
    try:
        if hasattr(bpy.ops.kaiserlich_tracker, "detect_adapt"):
            bpy.ops.kaiserlich_tracker.detect_adapt()
    except Exception:
        pass

    # Tracking
    try:
        run_track_cycle(context, max_frames=0, verbose=False)
    except Exception:
        pass

    # Track-Länge messen
    length = get_total_track_length(context, start_frame=start)

    # Neue Marker identifizieren & löschen
    try:
        new_markers = get_new_markers(context, old_markers)
        if new_markers:
            delete_tracks_by_names(context, new_markers)
    except Exception:
        pass

    # Frame zurücksetzen
    reset_to_frame(context, start)
    return int(length)


# ------------------------------------------------------------
# Ergebnisse speichern
# ------------------------------------------------------------
def save_result(context, prop: str, value: float):
    scene = context.scene
    key = f"kaiserlich_opt_{prop}"
    try:
        setattr(scene, key, float(value))
    except Exception:
        try:
            scene[key] = float(value)
        except Exception:
            pass


# ------------------------------------------------------------
# Basiswerte & Policies
# ------------------------------------------------------------
def get_min_threshold(context) -> float:
    return float(getattr(context.scene, "kaiserlich_min_threshold", 1e-8))


def baseline_target_value(context, active_prop: str, locked_prop: Optional[str], step_value: float) -> int:
    reset_all_thresholds(context, [])
    min_threshold = get_min_threshold(context)

    if locked_prop:
        set_scene_value(context, locked_prop, min_threshold)

    start_threshold = get_scene_value(context, active_prop) or 1.0
    end_threshold = start_threshold / step_value
    set_scene_value(context, active_prop, end_threshold)

    length = run_tracking_cycle(context)

    active_props = [active_prop] + ([locked_prop] if locked_prop else [])
    reset_all_thresholds(context, active_props)
    return int(length)


# ------------------------------------------------------------
# Hauptoperator: Auto Calibrate
# ------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung aller Tracking-Thresholds
       mit minimalem Logging.
       Nur Ausgaben:
         [AutoCal] name | thr=value | len=length | step=step_value
    """
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto Calibrate Thresholds"
    bl_description = "Kalibriert Threshold-Werte stufenbasiert, minimalistisch protokolliert."
    bl_options = {"REGISTER", "INTERNAL"}

    _opt: Dict[str, float] = None

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        tracking = getattr(clip, "tracking", None)
        if tracking is None or len(tracking.tracks) == 0:
            try:
                bpy.ops.kaiserlich_tracker.detect_adapt()
            except Exception:
                self.report({'WARNING'}, "Keine Tracks und Detect Adapt nicht verfügbar.")
                return {'CANCELLED'}

        self._opt = {}
        self._short_test(context)

        for prop, value in (self._opt or {}).items():
            save_result(context, prop, value)

        self.report({"INFO"}, "Auto-Calibrate abgeschlossen.")
        return {"FINISHED"}

    # --------------------------------------------------------
    # Kurztest (findet relevante Thresholds)
    # --------------------------------------------------------
    def _short_test(self, context):
        current_index = 0
        min_threshold = get_min_threshold(context)

        while current_index < len(THRESH_LIST):
            thresh = THRESH_LIST[current_index]
            props = thresh["props"]

            # --- Doppelwerte ---
            if len(props) == 2:
                pA, pB = props

                # Beide min
                set_scene_value(context, pA, min_threshold)
                set_scene_value(context, pB, min_threshold)
                len_min = run_tracking_cycle(context)
                reset_all_thresholds(context, [pA, pB])

                # Beide max
                set_scene_value(context, pA, 1.0)
                set_scene_value(context, pB, 1.0)
                len_max = run_tracking_cycle(context)
                reset_all_thresholds(context, [pA, pB])

                if len_max > len_min:
                    # Test A
                    set_scene_value(context, pB, min_threshold)
                    print(f"[AutoCal] Start Haupttest für '{pA}' (locked={pB})")
                    self._main_test(context, active_prop=pA, locked_prop=pB)
                    reset_all_thresholds(context, [pA, pB])

                    # Test B
                    set_scene_value(context, pA, min_threshold)
                    print(f"[AutoCal] Start Haupttest für '{pB}' (locked={pA})")
                    self._main_test(context, active_prop=pB, locked_prop=pA)
                    reset_all_thresholds(context, [pA, pB])
                else:
                    current_index += 1
                    continue

            # --- Einzelparameter ---
            elif len(props) == 1:
                p = props[0]

                set_scene_value(context, p, 1.0)
                len_high = run_tracking_cycle(context)
                reset_all_thresholds(context, [p])

                set_scene_value(context, p, min_threshold)
                len_low = run_tracking_cycle(context)
                reset_all_thresholds(context, [p])

                if len_low > len_high:
                    print(f"[AutoCal] Start Haupttest für '{p}'")
                    self._main_test(context, active_prop=p)
                else:
                    current_index += 1
                    continue

            current_index += 1

    # --------------------------------------------------------
    # Haupttest (stufenweise Kalibrierung mit minimalem Log)
    # --------------------------------------------------------
    def _main_test(self, context, active_prop: str, locked_prop: Optional[str] = None):
        step_value = 140.0
        min_threshold = get_min_threshold(context)
        start_threshold = get_scene_value(context, active_prop) or 1.0
        lower_threshold = min_threshold

        target_value = baseline_target_value(context, active_prop, locked_prop, step_value)

        while step_value >= 1:
            pre_active = [active_prop] + ([locked_prop] if locked_prop else [])
            reset_all_thresholds(context, pre_active)

            if locked_prop:
                set_scene_value(context, locked_prop, min_threshold)

            current_start = start_threshold
            current_end = current_start / step_value
            set_scene_value(context, active_prop, current_end)

            track_len = run_tracking_cycle(context)

            # --- MINIMAL LOG ---
            print(f"[AutoCal] {active_prop} | thr={current_end:.8f} | len={track_len} | step={step_value:.3f}")

            reset_all_thresholds(context, pre_active)

            # Wechselkriterien
            if track_len == target_value:
                lower_threshold = current_end
                step_value /= 2.0
                if step_value < 1.0:
                    break
                continue

            elif track_len > target_value:
                target_value = track_len
                lower_threshold = current_end
                step_value /= 2.0
                if step_value < 1.0:
                    break
                continue

            elif current_end <= min_threshold:
                step_value /= 2.0
                if step_value < 1.0:
                    break
                continue

            else:
                start_threshold = current_end
                continue

        # Optional: Abschlusslog für bessere Übersicht
        print(f"[AutoCal] --- FINISHED: {active_prop} best={lower_threshold:.8f}")

        if self._opt is None:
            self._opt = {}
        self._opt[active_prop] = float(lower_threshold)


# ------------------------------------------------------------
# Register / Unregister
# ------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)
