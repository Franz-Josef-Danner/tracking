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
            print("[Kaiserlich Tracker][MasterCycle] ⚠️ Kein schwacher Frame gefunden – führe globales Filter-Cleanup durch ...")

            try:
                # ------------------------------------------------------------------
                # Gültigen CLIP_EDITOR Kontext sicherstellen
                # ------------------------------------------------------------------
                area, region, space = find_clip_editor_area(context)
                if not area or not region or not space:
                    raise RuntimeError("Keine CLIP_EDITOR Area gefunden – filter_tracks benötigt gültigen Kontext.")

                # ------------------------------------------------------------------
                # Filterprozesse im gesicherten Kontext ausführen
                # ------------------------------------------------------------------
                with bpy.context.temp_override(area=area, region=region, space_data=space):
                    deleted_names_all, deleted_count_all = filter_and_delete_all_tracks(threshold=30.0)
                    print(f"[Kaiserlich Tracker][MasterCycle] FilterAll abgeschlossen – {deleted_count_all} Tracks gelöscht.")

                    filter_problematic_tracks(context, threshold=10.0)
                    print("[Kaiserlich Tracker][MasterCycle] FilterTracks abgeschlossen.")

                # 3) Erneuter Versuch, einen schwachen Frame zu finden
                frame = find_first_weak_frame(context)
                if frame is None:
                    print("[Kaiserlich Tracker][MasterCycle] ❌ Auch nach Filter kein schwacher Frame gefunden – beende Zyklus.")
                    self.report({'INFO'}, "[MasterCycle] Kein schwacher Frame nach Filterung – Vorgang abgeschlossen.")
                    return {'FINISHED'}
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
                            print(f"[Kaiserlich Tracker][MasterCycle] 🔄 '{k}' gelöscht (Threshold-Cache zurückgesetzt).")

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
                        print("[Kaiserlich Tracker][MasterCycle] ✅ Threshold-Properties global auf 1.0 zurückgesetzt.")
                    except Exception as e:
                        print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler beim Reset der Scene-Props: {e}")
                except ValueError as e:
                    self.report({'WARNING'}, str(e))
                    
                print(f"[Kaiserlich Tracker][MasterCycle] ✅ Neuer schwacher Frame gefunden nach Filterung: {frame}")
            except Exception as ex:
                print(f"[Kaiserlich Tracker][MasterCycle] ❌ Fehler während Filter/Retry-Prozess: {ex!r}")
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

        print(f"[Kaiserlich Tracker][Master] Playhead gesetzt auf Frame {frame} – Starte ShortTest.")
        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt – ShortTest wird gestartet.")

        # Operator-Aufruf (vollständiger ShortTest)
        # Erwartete ID: bl_idname = "kaiserlich_tracker.master_shorttest_operator"
        op_id = "kaiserlich_tracker.master_shorttest_operator"
        try:
            # Sanity-Check: Ist der Operator registriert?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_shorttest_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_shorttest_operator.py"
                print(f"[Kaiserlich Tracker][Master] ⚠️ {msg}")
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            # Start
            bpy.ops.kaiserlich_tracker.master_shorttest_operator('INVOKE_DEFAULT')
            print("[Kaiserlich Tracker][Master] ShortTest erfolgreich gestartet.")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][Master] ⚠️ Fehler beim Starten des ShortTest: {ex!r}")
            self.report({'WARNING'}, f"Fehler beim Start des ShortTest: {ex}")

        return {'FINISHED'}

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
