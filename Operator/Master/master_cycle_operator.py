# Operator/master_cycle_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.filter_all_tracks import filter_and_delete_all_tracks
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes

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
                # 1) Globaler Filter für alle Tracks
                deleted_names_all, deleted_count_all = filter_and_delete_all_tracks(threshold=30.0)
                print(f"[Kaiserlich Tracker][MasterCycle] FilterAll abgeschlossen – {deleted_count_all} Tracks gelöscht.")

                # 2) Lokaler Filter für problematische Tracks
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
