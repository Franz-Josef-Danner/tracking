import bpy
from bpy.types import Operator, Context
from typing import Optional, List, Set

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.filter_all_tracks import filter_and_delete_all_tracks
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.util_clip import get_active_clip

class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Setzt den Playhead auf den ersten Frame mit der geringsten Markeranzahl"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        print("\n[Kaiserlich Tracker][MasterCycle] ▶️ Start – prüfe auf schwachen Frame...")
        frame = find_first_weak_frame(context)
        print(f"[Kaiserlich Tracker][MasterCycle] Frame-Ergebnis: {frame}")

        # ------------------------------------------------------------------
        # Wenn kein Frame gefunden wurde → regulär beenden
        # ------------------------------------------------------------------
        if frame is None:
            print("[Kaiserlich Tracker][MasterCycle] ⚠️ Kein schwacher Frame gefunden – starte Filter-Cleanup-Sequenz...")

            try:
                # ------------------------------------------------------------------
                # 1) Gültigen Clip & Clip-Editor-Kontext bestimmen
                # ------------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step1] Ermittle aktiven Clip...")
                clip = get_active_clip(context, allow_global_fallback=True)
                if clip:
                    print(f"[Kaiserlich Tracker][MasterCycle] ✅ Aktiver Clip erkannt: {clip.name}")
                else:
                    raise RuntimeError("❌ Kein aktiver MovieClip verfügbar.")

                print("[Kaiserlich Tracker][MasterCycle] [Step2] Suche CLIP_EDITOR Area...")
                area = next((a for a in context.screen.areas if a.type == "CLIP_EDITOR"), None)
                if not area:
                    raise RuntimeError("❌ Kein CLIP_EDITOR im aktuellen Screen gefunden.")
                print(f"[Kaiserlich Tracker][MasterCycle] ✅ CLIP_EDITOR gefunden: {area}")

                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if not region:
                    raise RuntimeError("❌ Keine gültige Region für CLIP_EDITOR gefunden.")
                print(f"[Kaiserlich Tracker][MasterCycle] ✅ Region gesetzt: {region.type}")

                # ------------------------------------------------------------------
                # Override-Kontext aufbauen
                # ------------------------------------------------------------------
                override = context.copy()
                override["area"] = area
                override["region"] = region
                override["space_data"] = area.spaces.active
                override["edit_movieclip"] = clip

                print("[Kaiserlich Tracker][MasterCycle] [Step3] Override-Kontext erfolgreich erstellt.")
                print(f"    • area: {override['area'].type}")
                print(f"    • region: {override['region'].type}")
                print(f"    • space_data: {type(override['space_data']).__name__}")
                print(f"    • clip: {clip.name}")

                # ------------------------------------------------------------------
                # 2) Globaler Filter mit gültigem Override
                # ------------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step4] Starte globalen Filter (filter_and_delete_all_tracks)...")
                with bpy.context.temp_override(**override):
                    deleted_names_all, deleted_count_all = filter_and_delete_all_tracks(threshold=30.0)
                    print(f"[Kaiserlich Tracker][MasterCycle] ✅ FilterAll abgeschlossen – {deleted_count_all} Tracks gelöscht.")

                # ------------------------------------------------------------------
                # 3) Problematische Tracks filtern
                # ------------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step5] Starte lokalen Filter (filter_problematic_tracks)...")
                with bpy.context.temp_override(**override):
                    filter_problematic_tracks(bpy.context, threshold=10.0)
                print("[Kaiserlich Tracker][MasterCycle] ✅ FilterTracks abgeschlossen.")

                # ------------------------------------------------------------------
                # 4) Erneuter Versuch: schwachen Frame finden
                # ------------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step6] Suche erneut nach schwachem Frame...")
                frame = find_first_weak_frame(context)
                if frame is None:
                    print("[Kaiserlich Tracker][MasterCycle] ❌ Auch nach Filter kein schwacher Frame gefunden – Zyklus wird beendet.")
                    self.report({'INFO'}, "[MasterCycle] Kein schwacher Frame nach Filterung – Vorgang abgeschlossen.")
                    return {'FINISHED'}

                print(f"[Kaiserlich Tracker][MasterCycle] ✅ Neuer schwacher Frame gefunden: {frame}")

                # ------------------------------------------------------------------
                # 5) Standardgrößen aktualisieren
                # ------------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step7] Aktualisiere Default Sizes...")
                try:
                    op, os, np, ns = update_default_sizes(context)
                    print(f"[Kaiserlich Tracker][MasterCycle] 🔧 Defaults aktualisiert: pattern {op}->{np}, search {os}->{ns}")
                    self.report({'INFO'}, f"[Defaults] pattern {op}->{np}, search {os}->{ns}")
                except ValueError as e:
                    print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler beim Update der Default Sizes: {e}")
                    self.report({'WARNING'}, str(e))

                # --------------------------------------------------------------
                # Reset aller Frame-basierten Threshold-Werte (DeepTest/ShortTest Cache)
                # --------------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle] [Step8] Lösche gespeicherte Threshold-Maps und Caches...")
                scene = context.scene
                reset_keys = ["frame_value_cache", "min_distance_values", "kaiserlich_best_thresholds"]
                for k in reset_keys:
                    if k in scene:
                        del scene[k]
                        print(f"[Kaiserlich Tracker][MasterCycle] 🔄 '{k}' gelöscht.")

                # Zusätzlich: alle relevanten Threshold-Props zurücksetzen
                print("[Kaiserlich Tracker][MasterCycle] [Step9] Setze globale Threshold Properties zurück...")
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
                    print("[Kaiserlich Tracker][MasterCycle] ✅ Threshold Properties erfolgreich auf 1.0 gesetzt.")
                except Exception as e:
                    print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler beim Setzen der Scene Props: {e}")

            except Exception as ex:
                print(f"[Kaiserlich Tracker][MasterCycle] ❌ Ausnahme während Filter/Retry-Prozess:")
                import traceback
                traceback.print_exc()
                print(f"[Kaiserlich Tracker][MasterCycle] Exception-Objekt: {ex!r}")
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
        except Exception as e:
            print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler beim Setzen des Playhead: {e}")

        print(f"[Kaiserlich Tracker][MasterCycle] ▶️ Playhead gesetzt auf Frame {frame} – Starte ShortTest.")
        self.report({'INFO'}, f"[Master] Playhead auf Frame {frame} gesetzt – ShortTest wird gestartet.")

        # ------------------------------------------------------------------
        # Operator-Aufruf (ShortTest)
        # ------------------------------------------------------------------
        op_id = "kaiserlich_tracker.master_shorttest_operator"
        try:
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_shorttest_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_shorttest_operator.py"
                print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ {msg}")
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            bpy.ops.kaiserlich_tracker.master_shorttest_operator('INVOKE_DEFAULT')
            print("[Kaiserlich Tracker][MasterCycle] ✅ ShortTest erfolgreich gestartet.")
        except Exception as ex:
            print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ Fehler beim Starten des ShortTest: {ex!r}")
            import traceback
            traceback.print_exc()
            self.report({'WARNING'}, f"Fehler beim Start des ShortTest: {ex}")

        return {'FINISHED'}


# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
