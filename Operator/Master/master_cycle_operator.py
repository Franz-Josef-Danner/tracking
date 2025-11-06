# Operator/Master/master_cycle_operator.py
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
                    except Exception:
                        pass

                clip_obj = getattr(space, "clip", None)
                if clip_obj is None:
                    raise RuntimeError("[MasterCycle] Kein aktiver Clip im Kontext vorhanden.")

                # ------------------------------------------------------------------
                # Filter Tracks (problematische markieren & löschen)
                # ------------------------------------------------------------------
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    res = bpy.ops.clip.filter_tracks(track_threshold=30.0)

                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]

                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        deleted_count_all = delete_tracks_by_names(bpy.context, flagged_names)

                        # 🟡 LOG: Ausgabe der gelöschten Tracks
                        print(f"[MasterCycle][Delete] 🧹 {deleted_count_all} Tracks gelöscht:")
                        for name in flagged_names:
                            print(f"   └─ {name}")
                    else:
                        deleted_count_all = 0
                        print("[MasterCycle][Delete] Keine selektierten Tracks zum Löschen gefunden.")

                # ------------------------------------------------------------------
                # Zweite Filterstufe
                # ------------------------------------------------------------------
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        filter_problematic_tracks(context, threshold=10.0)
                    except Exception as ftrack_err:
                        print(f"[MasterCycle][Delete] ⚠️ Fehler beim zweiten Filterdurchlauf: {ftrack_err}")

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

                        bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                        self.report({'INFO'}, "[MasterCycle] Kein schwacher Frame – Resolve-Prozess gestartet.")
                        return {'FINISHED'}

                    except Exception as resolve_err:
                        self.report({'ERROR'}, f"Fehler beim Starten des Resolve-Operators: {resolve_err}")
                        return {'CANCELLED'}

                try:
                    op, os, np, ns = update_default_sizes(context)
                    self.report({'INFO'}, f"[Defaults] pattern {op}->{np}, search {os}->{ns}")

                    # Reset interner Cache-Werte
                    scene = context.scene
                    reset_keys = ["frame_value_cache", "min_distance_values", "kaiserlich_best_thresholds"]
                    for k in reset_keys:
                        if k in scene:
                            del scene[k]

                    # Threshold-Props zurücksetzen
                    from ...Helper.util_scene import set_scene_props
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
                except ValueError as e:
                    self.report({'WARNING'}, str(e))
                    
            except Exception as ex:
                self.report({'ERROR'}, f"Fehler bei Filterprozess: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # Wenn ein Frame gefunden wurde → Playhead setzen
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

        # Operator-Aufruf
        op_id = "kaiserlichtracker.master_deep_test_operator"
        try:
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_deep_test_operator.py"
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'WARNING'}, f"Fehler beim Start des ShortTest: {ex}")

        # ------------------------------------------------------------------
        # 🧮 Track-Qualität berechnen
        # ------------------------------------------------------------------
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"

            # UI Refresh
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()

        except Exception:
            quality_percent = 100.0

        # ------------------------------------------------------------------
        # 🧩 Marker-Fortschritt berechnen
        # ------------------------------------------------------------------
        try:
            from ...Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)
            self.report({'INFO'}, f"[Progress] Marker gesamt: {value}, Fortschritt: {perc:.1f}%")
        except Exception as progress_err:
            self.report({'WARNING'}, f"Fortschrittsberechnung fehlgeschlagen: {progress_err}")

        return {'FINISHED'}
    

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
