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
                # ----------------------------------------------------------
                # Sicheren CLIP_EDITOR-Kontext herstellen
                # ----------------------------------------------------------
                window, area, region, space = find_clip_editor_area(getattr(getattr(context, "space_data", None), "clip", None))
                if window is None or area is None or region is None or space is None:
                    raise RuntimeError("Keine CLIP_EDITOR Area gefunden – filter_tracks benötigt gültigen Kontext.")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)
                print("[Kaiserlich Tracker][MasterCycle][CTX] ✓ CLIP_EDITOR gefunden "
                      f"(window={getattr(window, 'as_pointer', lambda: None)()}, "
                      f"area.type={getattr(area,'type',None)}, region.type={getattr(region,'type',None)}, "
                      f"space.clip.valid={bool(getattr(space,'clip',None))}, "
                      f"context.clip.valid={bool(clip_ref)})")

                # Sicherstellen, dass space.clip korrekt gesetzt ist
                if getattr(space, "clip", None) is None and clip_ref:
                    try:
                        space.clip = clip_ref
                        print("[Kaiserlich Tracker][MasterCycle][CTX] 🔄 space.clip wurde auf aktiven Clip gesetzt.")
                    except Exception as assign_err:
                        print(f"[Kaiserlich Tracker][MasterCycle][CTX] ⚠️ Konnte space.clip nicht setzen: {assign_err!r}")

                # Zusätzliche Validierung
                if getattr(space, "clip", None) is None:
                    print("[Kaiserlich Tracker][MasterCycle][CTX] ❌ space.clip bleibt None – Filter könnte fehlschlagen.")
                else:
                    print(f"[Kaiserlich Tracker][MasterCycle][CTX] ✅ Clip-Zuweisung bestätigt ({space.clip.name}).")

                # ----------------------------------------------------------
                # Deep Diagnostic: Context intern prüfen
                # ----------------------------------------------------------
                print("[Kaiserlich Tracker][MasterCycle][CTX-Check] Starte Context-Validierung …")
                try:
                    current_area = getattr(bpy.context, "area", None)
                    current_region = getattr(bpy.context, "region", None)
                    current_space = getattr(bpy.context, "space_data", None)
                    print(f"[Kaiserlich Tracker][MasterCycle][CTX-Check] Vor Override: "
                          f"area={getattr(current_area,'type',None)}, "
                          f"region={getattr(current_region,'type',None)}, "
                          f"space={getattr(current_space,'type',None)}, "
                          f"clip.valid={bool(getattr(current_space,'clip',None))})")
                except Exception as diag_err:
                    print(f"[Kaiserlich Tracker][MasterCycle][CTX-Check] ⚠️ Fehler bei Vor-Diagnose: {diag_err!r}")

                # ----------------------------------------------------------
                # Testweise Override-Diagnose: prüft, ob Zugriff auf clip möglich ist
                # ----------------------------------------------------------
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                        print("[Kaiserlich Tracker][MasterCycle][CTX-Test] 🔍 Innerhalb Override:")
                        print(f"    → area={getattr(bpy.context.area,'type',None)}")
                        print(f"    → region={getattr(bpy.context.region,'type',None)}")
                        print(f"    → space={getattr(bpy.context.space_data,'type',None)}")
                        print(f"    → clip.valid={bool(getattr(bpy.context.space_data,'clip',None))}")
                        tracking = getattr(getattr(bpy.context.space_data,'clip',None),'tracking',None)
                        print(f"    → tracking.valid={bool(tracking)}")
                except Exception as e_test:
                    print(f"[Kaiserlich Tracker][MasterCycle][CTX-Test] ⚠️ Fehler im Override-Test: {e_test!r}")

                print("[Kaiserlich Tracker][MasterCycle][CTX-Check] Context-Diagnose abgeschlossen.")
                # 1) Globaler Filter für alle Tracks (mit Override)
                print("[Kaiserlich Tracker][MasterCycle][CTX-LIVE] 🔍 Vor FilterAll:")
                print(f"    area={getattr(area,'type',None)}, region={getattr(region,'type',None)}, "
                      f"space={getattr(space,'type',None)}, clip.valid={bool(getattr(space,'clip',None))}, "
                      f"tracking.valid={bool(getattr(getattr(space,'clip',None),'tracking',None))}")

                # Kein temp_override hier, weil der Helper selbst eines erzeugt.
                clip_obj = getattr(space, "clip", None)
                if clip_obj is None:
                    raise RuntimeError("[MasterCycle] Kein aktiver Clip im Kontext vorhanden.")

                print(f"[Kaiserlich Tracker][MasterCycle][CTX-LIVE] ▶ Starte FilterAll direkt über Helper (Clip='{clip_obj.name}') ...")
                print(f"[Kaiserlich Tracker][MasterCycle][CTX-PreCall] window={getattr(window,'as_pointer',lambda:None)()}, "
                      f"area={getattr(area,'type',None)}, region={getattr(region,'type',None)}, "
                      f"space={getattr(space,'type',None)}, clip={getattr(clip_obj,'name',None)}")

                # ------------------------------------------------------------------
                # Bypass: direkter Operator-Call im gültigen Override-Kontext,
                # da der Helper intern veraltete Argument-Signatur nutzt.
                # ------------------------------------------------------------------
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                        print("[Kaiserlich Tracker][MasterCycle][Bypass] → Führe bpy.ops.clip.filter_tracks() direkt aus …")
                        res = bpy.ops.clip.filter_tracks(track_threshold=30.0)
                        print(f"[Kaiserlich Tracker][MasterCycle][Bypass] Ergebnis filter_tracks: {res}")

                        # Selektierte (= problematische) Tracks löschen
                        tracking = clip_obj.tracking
                        flagged_names = [t.name for t in tracking.tracks if t.select]
                        print(f"[Kaiserlich Tracker][MasterCycle][Bypass] {len(flagged_names)} Tracks markiert.")
                        if flagged_names:
                            from ...Helper.delete import delete_tracks_by_names
                            deleted_count_all = delete_tracks_by_names(bpy.context, flagged_names)
                            print(f"[Kaiserlich Tracker][MasterCycle][Bypass] 🗑️ {deleted_count_all} Tracks gelöscht.")
                        else:
                            deleted_count_all = 0
                            print("[Kaiserlich Tracker][MasterCycle][Bypass] Keine markierten Tracks – kein Löschvorgang.")
                except Exception as call_err:
                    print(f"[Kaiserlich Tracker][MasterCycle][Bypass] ❌ Fehler bei direktem Filter/Löschvorgang: {call_err!r}")
                    deleted_count_all = 0

                print("[Kaiserlich Tracker][MasterCycle][CTX-LIVE] 🔍 Vor FilterTracks:")
                print(f"    clip.valid={bool(getattr(space,'clip',None))}, tracking.valid={bool(getattr(getattr(space,'clip',None),'tracking',None))}")

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    print("[Kaiserlich Tracker][MasterCycle][CTX-LIVE] ▶ Innerhalb Override vor filter_problematic_tracks:")
                    print(f"       bpy.context.area={getattr(bpy.context.area,'type',None)}")
                    print(f"       bpy.context.region={getattr(bpy.context.region,'type',None)}")
                    print(f"       bpy.context.space_data={getattr(bpy.context.space_data,'type',None)}")
                    print(f"       clip.valid={bool(getattr(bpy.context.space_data,'clip',None))}")
                    print(f"       tracking.valid={bool(getattr(getattr(bpy.context.space_data,'clip',None),'tracking',None))}")
                    try:
                        # Clip vor Call prüfen
                        clip_obj2 = getattr(bpy.context.space_data, "clip", None)
                        print(f"[Kaiserlich Tracker][MasterCycle][CTX-LIVE] ▶ Verwende Clip '{getattr(clip_obj2,'name',None)}' für FilterTracks ...")
                        filter_problematic_tracks(context, threshold=10.0)
                        print("[Kaiserlich Tracker][MasterCycle][CTX-LIVE] ▶ filter_problematic_tracks erfolgreich ausgeführt.")
                    except Exception as ftrack_err:
                        print(f"[Kaiserlich Tracker][MasterCycle][CTX-LIVE] ❌ Fehler bei filter_problematic_tracks: {ftrack_err!r}")
                        print(f"[Kaiserlich Tracker][MasterCycle][CTX-LIVE] Diagnose: "
                              f"area={getattr(bpy.context.area,'type',None)}, "
                              f"region={getattr(bpy.context.region,'type',None)}, "
                              f"space={getattr(bpy.context.space_data,'type',None)}, "
                              f"clip.valid={bool(getattr(bpy.context.space_data,'clip',None))}")
                        raise

                # Nachprüfung: war das Filtering erfolgreich?
                if deleted_count_all == 0:
                    print("[Kaiserlich Tracker][MasterCycle][Diag] Keine Tracks entfernt – evtl. leere Tracking-Collection oder fehlender Context.")
                else:
                    print(f"[Kaiserlich Tracker][MasterCycle][Diag] {deleted_count_all} Tracks entfernt – Filterprozess aktiv.")

                # 3) Erneuter Versuch, einen schwachen Frame zu finden
                frame = find_first_weak_frame(context)
                if frame is None:
                    print("[Kaiserlich Tracker][MasterCycle] ❌ Auch nach Filter kein schwacher Frame gefunden – starte Resolve-Prozess …")
                    try:
                        op_id_resolve = "kaiserlich_tracker.master_resolve_operator"

                        # Prüfen, ob der Operator registriert ist
                        op_cls = bpy.ops
                        if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_resolve_operator"):
                            msg = f"Operator '{op_id_resolve}' nicht registriert. Prüfe bl_idname in Operator/Master/master_resolve_operator.py"
                            print(f"[Kaiserlich Tracker][MasterCycle] ⚠️ {msg}")
                            self.report({'ERROR'}, msg)
                            return {'CANCELLED'}

                        # Operator ausführen
                        print("[Kaiserlich Tracker][MasterCycle] ▶ Übergabe an master_resolve_operator ...")
                        bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                        print("[Kaiserlich Tracker][MasterCycle] ✅ master_resolve_operator erfolgreich gestartet.")
                        self.report({'INFO'}, "[MasterCycle] Kein schwacher Frame – Resolve-Prozess gestartet.")
                        return {'FINISHED'}

                    except Exception as resolve_err:
                        print(f"[Kaiserlich Tracker][MasterCycle] ❌ Fehler beim Starten des master_resolve_operator: {resolve_err!r}")
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
