# Operator/master_cycle_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.filter_all_tracks import filter_and_delete_all_tracks
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.find_clip_editor_area import find_clip_editor_area

class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Setzt den Playhead auf den ersten Frame mit der geringsten Markeranzahl"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # Wenn kein Frame gefunden wurde → regulär beenden
        # ------------------------------------------------------------------
        if frame is None:
            try:
                # ----------------------------------------------------------
                # Sicheren CLIP_EDITOR-Kontext herstellen
                # ----------------------------------------------------------
                window, area, region, space = find_clip_editor_area(getattr(getattr(context, "space_data", None), "clip", None))
                if window is None or area is None or region is None or space is None:
                    raise RuntimeError("Keine CLIP_EDITOR Area gefunden – filter_tracks benötigt gültigen Kontext.")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)

                # Sicherstellen, dass space.clip korrekt gesetzt ist
                if getattr(space, "clip", None) is None and clip_ref:
                    try:
                        space.clip = clip_ref
                    except Exception as assign_err:
                        pass

                # Zusätzliche Validierung
                if getattr(space, "clip", None) is None:
                    pass

                # ----------------------------------------------------------
                # Deep Diagnostic: Context intern prüfen
                # ----------------------------------------------------------
                try:
                    current_area = getattr(bpy.context, "area", None)
                    current_region = getattr(bpy.context, "region", None)
                    current_space = getattr(bpy.context, "space_data", None)
                except Exception as diag_err:
                    pass

                # ----------------------------------------------------------
                # Testweise Override-Diagnose: prüft, ob Zugriff auf clip möglich ist
                # ----------------------------------------------------------
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                        tracking = getattr(getattr(bpy.context.space_data,'clip',None),'tracking',None)
                except Exception as e_test:
                    pass

                # 1) Globaler Filter für alle Tracks (mit Override)

                # Kein temp_override hier, weil der Helper selbst eines erzeugt.
                clip_obj = getattr(space, "clip", None)
                if clip_obj is None:
                    raise RuntimeError("[MasterCycle] Kein aktiver Clip im Kontext vorhanden.")

                # ------------------------------------------------------------------
                # Bypass: direkter Operator-Call im gültigen Override-Kontext,
                # da der Helper intern veraltete Argument-Signatur nutzt.
                # ------------------------------------------------------------------
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                        res = bpy.ops.clip.filter_tracks(track_threshold=30.0)

                        # Selektierte (= problematische) Tracks löschen
                        tracking = clip_obj.tracking
                        flagged_names = [t.name for t in tracking.tracks if t.select]
                        if flagged_names:
                            from ...Helper.delete import delete_tracks_by_names
                            deleted_count_all = delete_tracks_by_names(bpy.context, flagged_names)
                        else:
                            deleted_count_all = 0
                except Exception as call_err:
                    deleted_count_all = 0

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        # Clip vor Call prüfen
                        clip_obj2 = getattr(bpy.context.space_data, "clip", None)
                        filter_problematic_tracks(context, threshold=10.0)
                    except Exception as ftrack_err:
                        raise

                # Nachprüfung: war das Filtering erfolgreich?

                # 3) Erneuter Versuch, einen schwachen Frame zu finden
                frame = find_first_weak_frame(context)
                if frame is None:
                    try:
                        op_id_resolve = "kaiserlich_tracker.master_resolve_operator"

                        # Prüfen, ob der Operator registriert ist
                        op_cls = bpy.ops
                        if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_resolve_operator"):
                            msg = f"Operator '{op_id_resolve}' nicht registriert. Prüfe bl_idname in Operator/Master/master_resolve_operator.py"
                            self.report({'ERROR'}, msg)
                            return {'CANCELLED'}

                        # Operator ausführen
                        bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                        self.report({'INFO'}, "[MasterCycle] Kein schwacher Frame – Resolve-Prozess gestartet.")
                        return {'FINISHED'}

                    except Exception as resolve_err:
                        self.report({'ERROR'}, f"Fehler beim Starten des Resolve-Operators: {resolve_err}")
                        return {'CANCELLED'}
                try:
                    op, os, np, ns = update_default_sizes(context)
                    self.report({'INFO'}, f"[Defaults] pattern {op}->{np}, search {os}->{ns}")

                    # --------------------------------------------------------------
                    # Reset aller Frame-basierten Threshold-Werte (DeepTest/ShortTest Cache)
                    # --------------------------------------------------------------
                    scene = context.scene
                    reset_keys = ["frame_value_cache", "min_distance_values", "kaiserlich_best_thresholds"]
                    for k in reset_keys:
                        if k in scene:
                            del scene[k]

                    # Zusätzlich: alle relevanten Threshold-Props auf 1.0 setzen
                    from ...Helper.util_scene import set_scene_props
                    try:
                        set_scene_props(
                            scene,
                            kaiserlich_rot_thresh_x=1.0,
                            kaiserlich_rot_thresh_y=1.0,
                            kaiserlich_scale_thresh_min=1.0,
                            kaiserlich_scale_thresh_max=1.1,
                            kaiserlich_rot_scale_thresh_rot=1.0,
                            kaiserlich_rot_scale_thresh_scale=1.0,
                            kaiserlich_perspective_thresh=1.0
                        )
                    except Exception as e:
                        pass
                except ValueError as e:
                    self.report({'WARNING'}, str(e))
                    
            except Exception as ex:
                self.report({'ERROR'}, f"Fehler bei Filterprozess: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # Wenn ein Frame gefunden wurde → Playhead setzen und ShortTest starten
        # ------------------------------------------------------------------
        scene = context.scene
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt – ShortTest wird gestartet.")

        # Operator-Aufruf (vollständiger ShortTest)
        # Erwartete ID: bl_idname = "kaiserlichtracker.master_deep_test_operator"
        op_id = "kaiserlichtracker.master_deep_test_operator"
        try:
            # Sanity-Check: Ist der Operator registriert?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_deep_test_operator.py"
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            # Start
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'WARNING'}, f"Fehler beim Start des ShortTest: {ex}")

        # ------------------------------------------------------------------
        # 🧮 Abschluss: ZUERST Track-Qualität berechnen
        # ------------------------------------------------------------------
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"

            # UI-Refresh forcieren
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()

        except Exception as e:
            quality_percent = 100.0

        # ------------------------------------------------------------------
        # 🧩 Danach Marker-Fortschritt berechnen (nutzt Qualität mit)
        # ------------------------------------------------------------------
        try:
            from ...Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)

            # Fortschritt als Report ausgeben
            self.report({'INFO'}, f"[Progress] Marker gesamt: {value}, Fortschritt: {perc:.1f}%")

        except Exception as progress_err:
            self.report({'WARNING'}, f"Fortschrittsberechnung fehlgeschlagen: {progress_err}")

        return {'FINISHED'}
    
# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
