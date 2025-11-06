# Operator/master_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.bootstrap import run_bootstrap  # <--- Bootstrap importieren

class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "Master Operator"
    bl_description = "Setzt den Playhead auf den ersten Frame mit der geringsten Markeranzahl"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        # ------------------------------------------------------------------
        # Bootstrap ausführen, um Startparameter zu berechnen
        # ------------------------------------------------------------------
        scene = context.scene
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25))
        params = run_bootstrap(context, ef_target)
        if params:
            scene["bootstrap_params"] = params
            print(f"[Kaiserlich Tracker][Bootstrap] Initialisiert mit {params}")
        else:
            print("[Kaiserlich Tracker][Bootstrap] ⚠️ Bootstrap konnte nicht ausgeführt werden (kein aktiver Clip).")

        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # Wenn kein Frame gefunden wurde → regulär beenden
        # ------------------------------------------------------------------
        if frame is None:
            self.report({'INFO'}, "[Master] Kein schwacher Frame gefunden oder Marker-Ziel nicht unterschritten.")
            print("[Kaiserlich Tracker][Master] Kein schwacher Frame gefunden – DeepTest wird NICHT gestartet.")
            return {'FINISHED'}

        # ------------------------------------------------------------------
        # Wenn ein Frame gefunden wurde → Playhead setzen und DeepTest starten
        # ------------------------------------------------------------------
        scene = context.scene
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        print(f"[Kaiserlich Tracker][Master] Playhead gesetzt auf Frame {frame} – Starte DeepTest.")
        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt – DeepTest wird gestartet.")

        # Operator-Aufruf (vollständiger DeepTest)
        # Erwartete ID: bl_idname = "kaiserlich_tracker.master_deep_test_operator"
        op_id = "kaiserlich_tracker.master_deep_test_operator"
        try:
            # Sanity-Check: Ist der Operator registriert?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_deep_test_operator.py"
                print(f"[Kaiserlich Tracker][Master] ⚠️ {msg}")
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            # Start
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
            print("[Kaiserlich Tracker][Master] DeepTest erfolgreich gestartet.")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][Master] ⚠️ Fehler beim Starten des DeepTest: {ex!r}")
            self.report({'WARNING'}, f"Fehler beim Start des DeepTest: {ex}")
        # ------------------------------------------------------------------
        # 🧮 Abschluss: Marker-Fortschritt berechnen und in Szene-Properties schreiben
        # ------------------------------------------------------------------
        try:
            from ..Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)
            print(f"[Kaiserlich Tracker][MasterCycle] 📊 Marker-Fortschritt berechnet: {value} Marker ({perc:.2f}%)")

            # Fortschritt als Report ausgeben
            self.report({'INFO'}, f"[Progress] Marker gesamt: {value}, Fortschritt: {perc:.1f}%")

        except Exception as progress_err:
            print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler bei compute_marker_progress: {progress_err!r}")
            self.report({'WARNING'}, f"Fortschrittsberechnung fehlgeschlagen: {progress_err}")

        # Abschlussmeldung
        print("[Kaiserlich Tracker][MasterCycle] ✅ Vorgang vollständig abgeschlossen.")
        # ------------------------------------------------------------------
        # Track-Qualitätsbewertung (Prozentwert in UI schreiben)
        # ------------------------------------------------------------------
        try:
            from ..Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            percent = f"{int(round(metrics['prozent']))}%"
            context.scene.kaiserlich_quality_percent = percent
            print(f"[Kaiserlich Tracker][MasterCycle] 🎯 Track Quality: {percent}")

            # UI-Refresh forcieren
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
        except Exception as e:
            print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler bei Qualitätsanalyse: {e}")
        return {'FINISHED'}

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_operator)
