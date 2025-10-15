import bpy
from typing import List
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import detect_features
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
            # Fallback: Clip suchen
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
    
        # Property setzen
        setattr(scene, "kaiserlich_rot_thresh_y", ry)
        scene.update_tag()
    
        # UI aktualisieren
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
    
        if self.verbose:
            print(f"[Kaiserlich Tracker][AutoCalibrate] SET kaiserlich_rot_thresh_y={ry:.8f}")

    def _log_test(self, prop_name: str, value: float):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", f"TEST {prop_name}={value:.8f}")

    
    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def _detect_track_length(self, context, start_frame: int) -> int:
        """Snapshot → Detect → Track → Length → Delete."""
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
        

        # Init aller Properties
        for p in self._threshold_props:
            if hasattr(scene, p):
                self._set_prop(scene, p, 1.0)

        # Globale Baseline
        reset_to_frame(context, start_frame)
        baseline_length = self._detect_track_length(context, start_frame)
        

        # ==================================================
        # HAUPTSCHLEIFE pro Property
        # ==================================================
        handled_props = set()
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue

            # Bereits im Kombitest erledigt?
            if prop_name in handled_props:
                continue

            # Rot-X NICHT testen (am Ende abgeleitet)
            # kaiserlich_rot_thresh_x wird getestet; kaiserlich_rot_thresh_y wird später aus ihm abgeleitet

            # ==================================================
            # SPEZIALFALL: scale_thresh_min + scale_thresh_max
            # ==================================================
            if prop_name in {"kaiserlich_scale_thresh_min", "kaiserlich_rot_scale_thresh_rot"}:
                # Paare definieren
                if prop_name == "kaiserlich_scale_thresh_min":
                    other_prop = "kaiserlich_scale_thresh_max"
                else:
                    other_prop = "kaiserlich_rot_scale_thresh_scale"

                reset_to_frame(context, start_frame)

                # --- Initialisierung ---
                self._set_prop(scene, prop_name, 1.0)
                self._set_prop(scene, other_prop, 1.0)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._log_test(other_prop, getattr(scene, other_prop))

                # Kurztest (Neutral vs Minimum)
                reset_to_frame(context, start_frame)
                length_neutral = self._detect_track_length(context, start_frame)
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                reset_to_frame(context, start_frame)
                length_min = self._detect_track_length(context, start_frame)

                if length_min <= length_neutral:
                    self._set_prop(scene, prop_name, 1.0)
                    self._set_prop(scene, other_prop, 1.0)
                    handled_props.update({prop_name, other_prop})
                    continue

                # ==================================================
                # TEIL 1: erster Parameter (prop_name)
                # ==================================================
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                self._log_test(other_prop, getattr(scene, other_prop))

                reset_to_frame(context, start_frame)
                best_value = current_value = 1.0
                best_score = sg_prev = self._detect_track_length(context, start_frame)

                down_steps = [s for s in self._steps if s < 0]
                for step in down_steps:
                    change_detected = False
                    while True:
                        new_value = self._round(current_value * (1.0 + step), 8)
                        if new_value <= self.MIN_THRESHOLD:
                            break

                        self._set_prop(scene, prop_name, new_value)
                        self._log_test(prop_name, getattr(scene, prop_name))
                        reset_to_frame(context, start_frame)
                        sgn = self._detect_track_length(context, start_frame)

                        # Phase 1: Veränderungssuche
                        if not change_detected:
                            if sgn > sg_prev:
                                # ✅ Nur Verbesserung gilt als Veränderung
                                change_detected = True
                                best_score = sgn
                                best_value = new_value
                                sg_prev = sgn
                                current_value = new_value
                                continue
                            elif sgn < sg_prev:
                                # ❌ Verschlechterung ignorieren, weitersuchen
                                self._log(f"Ignoriere Verschlechterung ({sgn} < {sg_prev}) bei {prop_name}")
                                current_value = new_value
                                continue
                            else:
                                # Keine Veränderung, weitersuchen
                                current_value = new_value
                                continue


                        # Phase 2: Feinsuche
                        if sgn > best_score:
                            best_score = sgn
                            best_value = new_value
                            sg_prev = sgn
                            current_value = new_value
                            continue
                        elif sgn == best_score:
                            current_value = best_value
                            break
                        else:
                            current_value = best_value
                            break

                reset_to_frame(context, start_frame)
                self._set_prop(scene, prop_name, best_value)
                self._log_test(prop_name, getattr(scene, prop_name))

                # ==================================================
                # TEIL 2: zweiter Parameter (other_prop)
                # ==================================================
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._set_prop(scene, other_prop, 1.0)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._log_test(other_prop, getattr(scene, other_prop))
                reset_to_frame(context, start_frame)

                best_value = current_value = 1.0
                best_score = sg_prev = self._detect_track_length(context, start_frame)

                for step in down_steps:
                    change_detected = False
                    while True:
                        new_value = self._round(current_value * (1.0 + step), 8)
                        if new_value <= self.MIN_THRESHOLD:
                            break

                        self._set_prop(scene, other_prop, new_value)
                        self._log_test(other_prop, getattr(scene, other_prop))
                        reset_to_frame(context, start_frame)
                        sgn = self._detect_track_length(context, start_frame)

                        # Phase 1: Veränderungssuche
                        if not change_detected:
                            if sgn > sg_prev:
                                # ✅ Nur Verbesserung gilt als Veränderung
                                change_detected = True
                                best_score = sgn
                                best_value = new_value
                                sg_prev = sgn
                                current_value = new_value
                                continue
                            elif sgn < sg_prev:
                                # ❌ Verschlechterung ignorieren, weitersuchen
                                self._log(f"Ignoriere Verschlechterung ({sgn} < {sg_prev}) bei {prop_name}")
                                current_value = new_value
                                continue
                            else:
                                # Keine Veränderung, weitersuchen
                                current_value = new_value
                                continue


                        # Phase 2: Feinsuche
                        if sgn > best_score:
                            best_score = sgn
                            best_value = new_value
                            sg_prev = sgn
                            current_value = new_value
                            continue
                        elif sgn == best_score:
                            current_value = best_value
                            break
                        else:
                            current_value = best_value
                            break

                reset_to_frame(context, start_frame)
                self._set_prop(scene, other_prop, best_value)
                self._log_test(other_prop, getattr(scene, other_prop))

                handled_props.update({prop_name, other_prop})
                continue
        
                # ---------- Kurztest ----------
                
                reset_to_frame(context, start_frame)
        
                # 1️⃣ Beide auf 1.0
                self._set_prop(scene, prop_name, 1.0)
                self._set_prop(scene, other_prop, 1.0)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._log_test(other_prop, getattr(scene, other_prop))
                length_neutral = self._detect_track_length(context, start_frame)
        
                # 2️⃣ Beide auf MIN
                reset_to_frame(context, start_frame)
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._log_test(other_prop, getattr(scene, other_prop))
                length_min = self._detect_track_length(context, start_frame)
        
                # nach Skip: neutralen Zustand wiederherstellen
                self._set_prop(scene, prop_name, 1.0)
                self._set_prop(scene, other_prop, 1.0)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._log_test(other_prop, getattr(scene, other_prop))
                handled_props.update({prop_name, other_prop})
                continue
    
                # ---------- Haupttest 1: scale_thresh_min ----------
                self._set_prop(scene, other_prop, self.MIN_THRESHOLD)
                self._log_test(other_prop, getattr(scene, other_prop))
                reset_to_frame(context, start_frame)
                sg_prev = self._detect_track_length(context, start_frame)
                current_value = 1.0
        
                for step in self._steps:
                    change_detected = False
                    iteration = 0
                    stagnation_count = 0

                    while True:
                        iteration += 1
                        new_value = self._round(current_value * (1.0 + step), 8)
                        if new_value <= self.MIN_THRESHOLD or new_value >= self.MAX_THRESHOLD:
                            break
        
                        self._set_prop(scene, prop_name, new_value)
                        self._log_test(prop_name, getattr(scene, prop_name))
                        reset_to_frame(context, start_frame)
                        sgn = self._detect_track_length(context, start_frame)

        
                        if not change_detected:
                            if sgn != sg_prev:
                                change_detected = True
                                if sgn > sg_prev:
                                    sg_prev = sgn
                                    current_value = new_value
                                    continue
                                else:
                                    break
                            else:
                                current_value = new_value
                                continue
        
                        if sgn > sg_prev:
                            sg_prev = sgn
                            stagnation_count = 0
                            current_value = new_value
                            continue
                        elif sgn == sg_prev:
                            stagnation_count += 1
                            if stagnation_count >= 1:
                                break
                            continue
                        else:
                            break
        
                # ---------- Haupttest 2: scale_thresh_max ----------
                self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
                self._log_test(prop_name, getattr(scene, prop_name))
                self._set_prop(scene, other_prop, 1.0)
                self._log_test(other_prop, getattr(scene, other_prop))
                reset_to_frame(context, start_frame)
                sg_prev = self._detect_track_length(context, start_frame)
                current_value = 1.0
        
                for step in self._steps:
                    change_detected = False
                    iteration = 0
                    stagnation_count = 0

                    while True:
                        iteration += 1
                        new_value = self._round(current_value * (1.0 + step), 8)
                        if new_value <= self.MIN_THRESHOLD or new_value >= self.MAX_THRESHOLD:
                            break
        
                        self._set_prop(scene, other_prop, new_value)
                        self._log_test(other_prop, getattr(scene, other_prop))
                        reset_to_frame(context, start_frame)
                        sgn = self._detect_track_length(context, start_frame)
        
                        if not change_detected:
                            if sgn != sg_prev:
                                change_detected = True
                                if sgn > sg_prev:
                                    sg_prev = sgn
                                    current_value = new_value
                                    continue
                                else:
                                    break
                            else:
                                current_value = new_value
                                continue
        
                        if sgn > sg_prev:
                            sg_prev = sgn
                            stagnation_count = 0
                            current_value = new_value
                            continue
                        elif sgn == sg_prev:
                            stagnation_count += 1
                            if stagnation_count >= 1:
                                break
                            continue
                        else:
                            break

                handled_props.update({prop_name, other_prop})
                continue  # danach weiter mit nächstem Threshold        

            # ==================================================
            # STANDARD-FALL: alle anderen Thresholds
            # ==================================================
            # Kurztest (MIN vs 1.0)
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
            self._log_test(prop_name, getattr(scene, prop_name))  # 🔹 NEU: Log für MIN-Test
            length_min = self._detect_track_length(context, start_frame)

            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, 1.0)
            self._log_test(prop_name, getattr(scene, prop_name))
            length_neutral = self._detect_track_length(context, start_frame)

            if length_min <= length_neutral:
                continue

            # Haupttest (nur abwärts, Veränderung → Verschlechterung → Rücksprung)
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, 1.0)
            self._log_test(prop_name, getattr(scene, prop_name))

            best_value = current_value = 1.0
            best_score = sg_prev = self._detect_track_length(context, start_frame)

            down_steps = [s for s in self._steps if s < 0]
            for step in down_steps:
                change_detected = False
                while True:
                    new_value = self._round(current_value * (1.0 + step), 8)
                    if new_value <= self.MIN_THRESHOLD:
                        break

                    self._set_prop(scene, prop_name, new_value)
                    self._log_test(prop_name, getattr(scene, prop_name))
                    reset_to_frame(context, start_frame)
                    sgn = self._detect_track_length(context, start_frame)

                    # Phase 1: Veränderungssuche
                    if not change_detected:
                        if sgn > sg_prev:
                            # ✅ Nur Verbesserung gilt als Veränderung
                            change_detected = True
                            best_score = sgn
                            best_value = new_value
                            sg_prev = sgn
                            current_value = new_value
                            continue
                        elif sgn < sg_prev:
                            # ❌ Verschlechterung ignorieren, weitersuchen
                            self._log(f"Ignoriere Verschlechterung ({sgn} < {sg_prev}) bei {prop_name}")
                            current_value = new_value
                            continue
                        else:
                            # Keine Veränderung, weitersuchen
                            current_value = new_value
                            continue


                    # Phase 2: Feinsuche
                    if sgn > best_score:
                        best_score = sgn
                        best_value = new_value
                        sg_prev = sgn
                        current_value = new_value
                        continue
                    elif sgn == best_score:
                        current_value = best_value
                        break
                    else:
                        current_value = best_value
                        break

            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, best_value)
            self._log_test(prop_name, getattr(scene, prop_name))
            final_length = self._detect_track_length(context, start_frame)

        # ✅ FIX 1: restore_selection am Ende
        reset_to_frame(context, start_frame)
        _restore_selection()

        # rot_thresh_y am Ende aus rot_thresh_x ableiten
        self._auto_set_rot_thresh_y(context)

        # ✅ FIX 2: return ganz am Ende der execute()
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()
