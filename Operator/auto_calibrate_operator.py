import bpy
from typing import List, Tuple
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kalibriert automatisch die Schwellenwerte für Bewegungsmodelle
    durch mehrstufige, adaptive Wiederholung mit Veränderungs- und Feintuning-Phase."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Führt stufenweise Threshold-Kalibrierung mit dynamischer Verbesserungssuche durch."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging während der Kalibrierung",
    )

    MIN_THRESHOLD: float = 1e-8
    MAX_THRESHOLD: float = 1.0

    _threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

    _steps = [-0.95, -0.80, -0.70, -0.60, -0.50, -0.40, -0.30, -0.20, -0.10, -0.05, -0.02, -0.01]

    # ---------------------------------------
    # Hilfsfunktionen
    # ---------------------------------------
    def _auto_set_rot_thresh_y(self, context):
        scene = getattr(context, "scene", None) or bpy.context.scene
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)

        if clip is None:
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for sp in area.spaces:
                            if sp.type == 'CLIP_EDITOR' and getattr(sp, "clip", None):
                                clip = sp.clip
                                break
                    if clip:
                        break
                if clip:
                    break

        if clip is None or not hasattr(clip, "size"):
            return
        if not hasattr(scene, "kaiserlich_rot_thresh_x"):
            return

        ha, va = clip.size
        if not va:
            return
        rx = float(getattr(scene, "kaiserlich_rot_thresh_x"))
        ry = min(1.0, self._round(rx * (ha / va)))
        setattr(scene, "kaiserlich_rot_thresh_y", ry)
        scene.update_tag()

        if self.verbose:
            print(f"[Kaiserlich Tracker][AutoCalibrate] SET kaiserlich_rot_thresh_y={ry:.8f}")

    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def _log_test(self, prop_name: str, value: float):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", f"TEST {prop_name}={value:.8f}")

    def _detect_track_length(self, context, start_frame: int) -> int:
        clip = context.space_data.clip
        tracking = clip.tracking
        old_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        bpy.ops.kaiserlich_tracker.detect_adapt()
        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        for tr in tracking.tracks:
            tr.select = tr.name in new_names
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        length = get_total_track_length(context, start_frame)
        delete_tracks_by_names(context, new_names)
        return length

    def _set_prop(self, scene, prop_name: str, value: float) -> float:
        v = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(value)))
        setattr(scene, prop_name, self._round(v))
        scene.update_tag()
        return getattr(scene, prop_name)

    # -----------------------------------------------------
    # Kernlogik mit 2 Phasen pro Stufe + Rollback(−2)
    # -----------------------------------------------------
    def _adaptive_search(self, context, scene, prop_name, start_frame, initial_value=1.0):
        """
        Pro Stufe:
          Phase 1 (Improve-only): Verschlechterung/Stagnation ignorieren, bis erste Verbesserung.
          Phase 2 (Validate): weiter iterieren bis Stagnation/Verschlechterung, dann Stufe beenden.
          Nach Stufenende: Rollback auf (best_index - 2), wenn möglich; sonst (best_index - 1) oder best.
        """
        reset_to_frame(context, start_frame)
        best_value = current_value = initial_value
        best_score = sg_prev = self._detect_track_length(context, start_frame)
        down_steps = [s for s in self._steps if s < 0]

        # komplette Historie über alle Stufen nicht nötig; pro Stufe fresh sammeln
        for step_index, step in enumerate(down_steps):
            self._log(f"[{prop_name}] Step={step:+.2f}")

            phase = 1  # 1 = Improve-only, 2 = Validate
            change_detected = False

            # Verlauf dieser Stufe: Liste von (value, score)
            history: List[Tuple[float, int]] = []

            # --- Baseline pro Stufe
            new_value = self._round(current_value * (1.0 + step), 8)
            self._set_prop(scene, prop_name, new_value)
            reset_to_frame(context, start_frame)
            stage_baseline = self._detect_track_length(context, start_frame)
            sg_prev = stage_baseline
            current_value = new_value
            history.append((current_value, sg_prev))
            self._log(f"[{prop_name}] Baseline → Value={new_value:.8f} | TrackLength={stage_baseline}")

            # --- Iteration innerhalb der Stufe
            while True:
                # nächster Versuchswert innerhalb derselben Stufe
                new_value = self._round(current_value * (1.0 + step), 8)

                # keine künstliche Untergrenze-Abbruchlogik hier
                self._set_prop(scene, prop_name, new_value)
                reset_to_frame(context, start_frame)
                sgn = self._detect_track_length(context, start_frame)
                self._log(f"[{prop_name}] Step={step:+.2f} | Value={new_value:.8f} | TrackLength={sgn}")

                # Verlauf fortschreiben
                history.append((new_value, sgn))

                if phase == 1:
                    # Verbesserungssuche
                    if sgn > sg_prev:
                        # erste Verbesserung → Phase 2
                        change_detected = True
                        best_score = sgn
                        best_value = new_value
                        sg_prev = sgn
                        current_value = new_value
                        self._log(f"[{prop_name}] Verbesserung erkannt → Phase 2 (Validate) startet.")
                        phase = 2
                        continue
                    else:
                        # keine Verbesserung → weiter testen
                        sg_prev = sgn
                        current_value = new_value
                        continue

                else:
                    # Phase 2: Validierung bis Stagnation/Verschlechterung
                    if sgn > best_score:
                        best_score = sgn
                        best_value = new_value
                        sg_prev = sgn
                        current_value = new_value
                        continue
                    else:
                        # Stagnation (==) oder Verschlechterung (<) → Stufe beenden
                        self._log(f"[{prop_name}] Stagnation/Verschlechterung → Stufe beenden & Rollback(-2).")
                        # Rollback-Logik: Index des besten Werts suchen
                        if history:
                            # best_idx in history finden
                            best_idx = max(range(len(history)), key=lambda i: history[i][1])
                            target_idx = max(0, best_idx - 2)  # zwei vor dem besten, falls möglich
                            rollback_value = history[target_idx][0]
                            current_value = rollback_value
                            # Setzen und sichern
                            self._set_prop(scene, prop_name, current_value)
                            reset_to_frame(context, start_frame)
                            _ = self._detect_track_length(context, start_frame)
                            self._log(f"[{prop_name}] Rollback auf Index {target_idx} (Value={current_value:.8f}).")
                        break  # Stufe verlassen

            # nach Stufenende: weiter zur nächsten Stufe
            continue

        return current_value

    # ---------------------------------------
    # Hauptausführung
    # ---------------------------------------
    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

        selected_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)

        # Init Properties
        for p in self._threshold_props:
            if hasattr(scene, p):
                self._set_prop(scene, p, 1.0)

        reset_to_frame(context, start_frame)
        _ = self._detect_track_length(context, start_frame)
        handled_props = set()

        # ==================================================
        # Hauptschleife
        # ==================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue
            if prop_name in handled_props:
                continue

            # ==================================================
            # DOPPEL-THRESHOLDS
            # ==================================================
            if prop_name in {"kaiserlich_scale_thresh_min", "kaiserlich_rot_scale_thresh_rot"}:
                if prop_name == "kaiserlich_scale_thresh_min":
                    other_prop = "kaiserlich_scale_thresh_max"
                else:
                    other_prop = "kaiserlich_rot_scale_thresh_scale"

                # Neutraltest
                self._set_prop(scene, prop_name, 1.0)
                self._set_prop(scene, other_prop, 1.0)
                reset_to_frame(context, start_frame)
                length_neutral = self._detect_track_length(context, start_frame)

                # Minimaltest (nur zur Entscheidung, ob Optimierung sinnvoll ist)
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                reset_to_frame(context, start_frame)
                length_min = self._detect_track_length(context, start_frame)

                if length_min <= length_neutral:
                    handled_props.update({prop_name, other_prop})
                    continue

                # TEIL 1: min/rot zuerst (anderer auf MIN, aber ohne MIN-Abbruch in der Stufe)
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                val1 = self._adaptive_search(context, scene, prop_name, start_frame)
                reset_to_frame(context, start_frame)
                self._set_prop(scene, prop_name, val1)

                # TEIL 2: max/scale danach (erster wieder auf MIN)
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._set_prop(scene, other_prop, 1.0)
                val2 = self._adaptive_search(context, scene, other_prop, start_frame)
                reset_to_frame(context, start_frame)
                self._set_prop(scene, other_prop, val2)

                handled_props.update({prop_name, other_prop})
                continue

            # ==================================================
            # STANDARD-THRESHOLDS
            # ==================================================
            # Neutraltest
            self._set_prop(scene, prop_name, 1.0)
            reset_to_frame(context, start_frame)
            length_neutral = self._detect_track_length(context, start_frame)

            # Minimaltest (nur Entscheidungsbasis)
            self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
            reset_to_frame(context, start_frame)
            length_min = self._detect_track_length(context, start_frame)

            if length_min <= length_neutral:
                continue

            final_val = self._adaptive_search(context, scene, prop_name, start_frame)
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, final_val)
            self._log_test(prop_name, getattr(scene, prop_name))

        reset_to_frame(context, start_frame)
        _restore_selection()
        self._auto_set_rot_thresh_y(context)
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()
