import bpy
from typing import List, Dict, Any, Optional
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.reset_helper import reset_all_thresholds, THRESH_LIST, set_scene_value, get_scene_value

# Direct import of the procedural tracking function used by the operator
from ..Operator.track_operator import track_cycle as run_track_cycle
# Detect-Operator optional über bpy.ops verwendet, kein harter Import nötig


# ------------------------------------------------------------
# Marker-Diff Utilities
# ------------------------------------------------------------
def get_new_markers(context, before_snapshot: List[Dict[str, Any]]) -> List[str]:
    """Vergleicht aktuellen Marker-Zustand mit before_snapshot und gibt Liste
    von neuen Track-Namen zurück (nur Namen zur Verwendung mit Delete)."""
    before_names = {m['track'] for m in before_snapshot}
    after = snapshot_active_markers(context)
    after_names = {m['track'] for m in after}
    new = list(after_names - before_names)
    return new


# ------------------------------------------------------------
# Tracking-Wrapper mit Snapshot / Cleanup
# ------------------------------------------------------------
def run_tracking_cycle(context) -> int:
    """Führt einen vollständigen Detect+Track-Durchlauf aus und liefert die Gesamtlänge.
    - Snapshot vor Detect, danach Track
    - Messung der Track-Länge
    - Löschen aller neuen Marker
    - Rücksetzen auf Start-Frame
    WICHTIG: Erwartet, dass relevante Scene-Properties VORHER gesetzt sind.
    """
    start = get_start_frame(context)
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        print("[AutoCal] Kein aktiver Clip - Tracklauf wird übersprungen.")
        return 0

    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        print("[AutoCal] Clip hat kein Tracking-Objekt - Länge=0")
        return 0

    # Snapshot vor Detect
    old_markers = snapshot_active_markers(context)

    # DETECT (falls registriert)
    try:
        if hasattr(bpy.ops.kaiserlich_tracker, "detect_adapt"):
            bpy.ops.kaiserlich_tracker.detect_adapt()
    except Exception as e:
        print(f"[AutoCal] detect_adapt Exception: {e}")

    # TRACK – funktionaler Call bevorzugt
    try:
        res = run_track_cycle(context, max_frames=0, verbose=False)
    except Exception as e:
        print(f"[AutoCal] Exception in track_cycle: {e}")
        res = {'CANCELLED'}

    # Track-Länge messen (ab Start)
    length = get_total_track_length(context, start_frame=start)

    # Neue Marker identifizieren & löschen
    try:
        new_markers = get_new_markers(context, old_markers)
        if new_markers:
            delete_tracks_by_names(context, new_markers)
    except Exception as e:
        print(f"[AutoCal] Fehler beim Löschen neuer Marker: {e}")

    # Playhead zurück
    reset_to_frame(context, start)
    return int(length)


# ------------------------------------------------------------
# Ergebnis-Commit am Ende
# ------------------------------------------------------------
def save_result(context, prop: str, value: float):
    """Speichert das finale Ergebnis eindeutig benannt in der Scene."""
    scene = context.scene
    key = f"kaiserlich_opt_{prop}"
    try:
        setattr(scene, key, float(value))
    except Exception:
        # Fallback in Custom-Prop
        try:
            scene[key] = float(value)
        except Exception:
            pass


# ------------------------------------------------------------
# Hilfswerte / Policies
# ------------------------------------------------------------
def get_min_threshold(context) -> float:
    """Dedizierte, globale Untergrenze. Fallback robust klein."""
    return float(getattr(context.scene, "kaiserlich_min_threshold", 1e-8))


def baseline_target_value(context, active_prop: str, locked_prop: Optional[str], step_value: float) -> int:
    """Neutraler Baseline-Lauf:
       - Vorlauf-Reset: alle auf 1.0
       - locked_prop = min
       - active_prop = (start/step_value)
       - run → length
       - Nachlauf-Reset: alle außer aktiv/locked auf 1.0
    """
    reset_all_thresholds(context, [])  # alle auf 1.0
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
# Hauptoperator
# ------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Threshold-Parameter mit:
       - Stufenlogik (start=140, halbieren)
       - 3 Wechselkriterien: Ziel erreicht / Ziel übertroffen / Untergrenze erreicht
       - Doppelwerte seriell (einer aktiv, anderer fixiert auf min)
       - Reset vor/nach jedem Lauf (alle nicht getesteten = 1.0)
       - Snapshot vor Detect, Löschung neuer Marker nach Track
       - Finale Werte erst am Ende committen
    """
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto Calibrate Thresholds"
    bl_description = "Kalibriert Tracking-Thresholds stufenbasiert und deterministisch"
    bl_options = {"REGISTER", "INTERNAL"}

    # Puffer für finale Ergebnisse (erst am Ende committen)
    _opt: Dict[str, float] = None

    def execute(self, context):
        # Sicherstellen, dass es überhaupt Tracks gibt (optional: minimalinvasiv)
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Movie Clip Editor.")
            return {'CANCELLED'}

        tracking = getattr(clip, 'tracking', None)
        if tracking is None or len(tracking.tracks) == 0:
            print("[AutoCal] Keine Tracks gefunden – starte automatischen Detect.")
            try:
                bpy.ops.kaiserlich_tracker.detect_adapt()
            except Exception as e:
                self.report({'WARNING'}, f"Detect Adapt fehlgeschlagen: {e}")
                return {'CANCELLED'}

            tracking = getattr(clip, 'tracking', None)
            if tracking is None or len(tracking.tracks) == 0:
                self.report({'WARNING'}, "Keine Tracks nach Detect erstellt – Abbruch.")
                return {'CANCELLED'}

        self._opt = {}

        # Kurztest (identifiziert sensible Gruppen/Parameter, behandelt Doppelwerte)
        self._short_test(context)

        # Finale Commit-Phase: Ergebnisse in Scene speichern
        for prop, value in (self._opt or {}).items():
            save_result(context, prop, value)

        self.report({"INFO"}, "Auto-Calibrate abgeschlossen.")
        return {"FINISHED"}

    # --------------------------------------------------------
    # Kurztest
    # --------------------------------------------------------
    def _short_test(self, context):
        current_index = 0
        min_threshold = get_min_threshold(context)

        while current_index < len(THRESH_LIST):
            thresh = THRESH_LIST[current_index]
            props = thresh["props"]

            # Doppelwerte
            if len(props) == 2:
                pA, pB = props

                # Baseline: beide minimal
                set_scene_value(context, pA, min_threshold)
                set_scene_value(context, pB, min_threshold)
                len_min = run_tracking_cycle(context)
                reset_all_thresholds(context, [pA, pB])

                # Vergleich: beide maximal
                set_scene_value(context, pA, 1.0)
                set_scene_value(context, pB, 1.0)
                len_max = run_tracking_cycle(context)
                reset_all_thresholds(context, [pA, pB])

                if len_max > len_min:
                    # 1) pA aktiv, pB fixiert
                    set_scene_value(context, pB, min_threshold)
                    self._main_test(context, active_prop=pA, locked_prop=pB)
                    reset_all_thresholds(context, [pA, pB])

                    # 2) pB aktiv, pA fixiert
                    set_scene_value(context, pA, min_threshold)
                    self._main_test(context, active_prop=pB, locked_prop=pA)
                    reset_all_thresholds(context, [pA, pB])
                else:
                    current_index += 1
                    continue

            # Einzelparameter
            elif len(props) == 1:
                p = props[0]

                # hoch
                set_scene_value(context, p, 1.0)
                len_high = run_tracking_cycle(context)
                reset_all_thresholds(context, [p])

                # niedrig
                set_scene_value(context, p, min_threshold)
                len_low = run_tracking_cycle(context)
                reset_all_thresholds(context, [p])

                if len_low > len_high:
                    self._main_test(context, active_prop=p)
                else:
                    current_index += 1
                    continue

            current_index += 1

    # --------------------------------------------------------
    # Haupttest – Stufenlogik (140 → /2 … bis < 1)
    # 3 Wechselkriterien: == target, > target, end_threshold <= min
    # Reset vor/nach jedem Lauf; Doppelwerte: locked_prop=min
    # --------------------------------------------------------
    def _main_test(self, context, active_prop: str, locked_prop: Optional[str] = None):
        step_value = 140.0
        min_threshold = get_min_threshold(context)

        # Ausgangswerte
        start_threshold = get_scene_value(context, active_prop) or 1.0
        lower_threshold = min_threshold

        # Sauberen Zielwert aus neutralem Baseline-Lauf bestimmen
        target_value = baseline_target_value(context, active_prop, locked_prop, step_value)

        while step_value >= 1:
            # --- VORLAUF-RESET: alle auf 1.0, außer aktiv/locked
            pre_active = [active_prop] + ([locked_prop] if locked_prop else [])
            reset_all_thresholds(context, pre_active)

            # Fixierten Parameter (falls vorhanden) setzen
            if locked_prop:
                set_scene_value(context, locked_prop, min_threshold)

            # Aktiven Parameter: nächster Kandidat
            current_start = start_threshold
            current_end = current_start / step_value
            set_scene_value(context, active_prop, current_end)

            # Tracking
            track_len = run_tracking_cycle(context)

            # --- NACHLAUF-RESET: alle außer aktiv/locked auf 1.0
            reset_all_thresholds(context, pre_active)

            # === Wechselkriterium 1: Ziel erreicht ===
            if track_len == target_value:
                lower_threshold = current_end
                step_value /= 2.0
                if step_value < 1.0:
                    break
                # Start bleibt unverändert (deine Spezifikation)
                continue

            # === Wechselkriterium 2: Ziel übertroffen ===
            elif track_len > target_value:
                target_value = track_len
                lower_threshold = current_end
                step_value /= 2.0
                if step_value < 1.0:
                    break
                # Start bleibt unverändert
                continue

            # === Wechselkriterium 3: Untergrenze erreicht ===
            elif current_end <= min_threshold:
                step_value /= 2.0
                if step_value < 1.0:
                    break
                # Start bleibt unverändert (bei Untergrenze wechselt nur die Stufe)
                continue

            # --- kein Wechselkriterium erfüllt → Reduktion fortsetzen ---
            else:
                # innerhalb dieser Stufe weiter: neuer Start = aktueller Endwert
                start_threshold = current_end
                continue

        # Ergebnis dieser Kalibrierung puffern (finales Commit am Ende in execute)
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
