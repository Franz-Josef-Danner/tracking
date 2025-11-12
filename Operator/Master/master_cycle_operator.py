# master_cycle_operator.py
import bpy
import uuid
import ast
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ...Helper.low_marker_frame import find_first_weak_frame
from ...Helper.filter_all_tracks import filter_and_delete_all_tracks
from ...Helper.filter_tracks import filter_problematic_tracks
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.find_clip_editor_area import find_clip_editor_area


# ===================================================================
# Zentrale Hilfsfunktion: UUID-basierte Track-Speicherung in Scene
# ===================================================================
def store_tracks_in_scene(scene, context, key="good_tracks"):
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    if not clip:
        clip = getattr(context.scene.tracking, "active", None)
    if not clip:
        return

    tracking = clip.tracking
    all_tracks = list(tracking.tracks)

    for k in (
        "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
        "best_tracks", "best_tracks_names", "best_tracks_uuid_map"
    ):
        if k in scene:
            del scene[k]

    uuid_list, name_list, uuid_map = [], [], {}
    for t in all_tracks:
        uid = str(uuid.uuid4())
        uuid_list.append(uid)
        name_list.append(t.name)
        uuid_map[uid] = t.name

    scene[key] = uuid_list
    scene[f"{key}_names"] = name_list
    scene[f"{key}_uuid_map"] = str(uuid_map)


# ===================================================================
# Haupt-Operator
# ===================================================================
class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – Sets the playhead to the frame with the fewest active markers"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Sets the playhead to the first frame with the lowest number of active markers"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------
    # Interne Clip-Refresh-Helfer
    # ------------------------------------------------------------------
    def _force_clip_refresh(self, context: Context, clip) -> None:
        try:
            window, area, region, space = find_clip_editor_area(
                getattr(getattr(context, "space_data", None), "clip", None) or clip
            )
        except Exception:
            return

        try:
            if space:
                space.clip = clip
            context.view_layer.update()
        except Exception:
            pass

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
                    bpy.ops.clip.select_all(action='DESELECT')
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rebuild Good Tracks
    # ------------------------------------------------------------------
    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        scene = context.scene
        clip = (
            getattr(getattr(context, "space_data", None), "clip", None)
            or getattr(context, "edit_movieclip", None)
            or getattr(getattr(scene, "tracking", None), "active", None)
        )
        if not clip or not hasattr(clip, "tracking"):
            return
        self._force_clip_refresh(context, clip)
        store_tracks_in_scene(scene, context, key="good_tracks")

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self, context: Context):
        scene = context.scene

        # ===============================================================
        # Scene-Bereinigung (alte Daten entfernen)
        # ===============================================================
        try:
            print("\n[MasterCycle][Scene] --- Starte Bereinigung alter Scene-Keys ---")
            keys_to_delete = [
                "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
                "best_tracks", "best_tracks_names", "best_tracks_uuid_map",
                "calibrate_tracks", "calibrate_tracks_names", "calibrate_tracks_uuid_map",
                "frame_value_cache", "kaiserlich_best_thresholds"
            ]
            for _k in keys_to_delete:
                if _k in scene:
                    print(f"[MasterCycle][Scene] Entferne Scene Key: {_k}")
                    del scene[_k]
        except Exception:
            print("[MasterCycle][Scene] WARNUNG: Fehler beim Bereinigen der Scene-Keys")
            pass

        print("[MasterCycle] Suche ersten schwachen Frame ...")
        frame = find_first_weak_frame(context)
        print(f"[MasterCycle] Ergebnis Weak Frame: {frame}")

        # ===================================================================
        # MOTION LIST → MOTION VALUE
        # ===================================================================
        if frame is None:
            print("[MasterCycle][Motion] Kein Weak Frame gefunden, prüfe Motion-Daten ...")
            try:
                existing_motion_value = scene.get("motion_value")
                if existing_motion_value and isinstance(existing_motion_value, dict):
                    print("[MasterCycle][Motion] Bestehende motion_value gefunden – wird verwendet")
                    motion_value = existing_motion_value
                else:
                    raw_motion = scene.get("motion_list")
                    motion_list = None
                    print(f"[MasterCycle][Motion] Rohdaten motion_list Typ: {type(raw_motion).__name__}")

                    # --- Robust Parsing ---
                    if raw_motion:
                        if isinstance(raw_motion, str):
                            try:
                                parsed = ast.literal_eval(raw_motion)
                                if isinstance(parsed, dict):
                                    motion_list = [parsed]
                                elif isinstance(parsed, (list, tuple)):
                                    motion_list = list(parsed)
                                print(f"[MasterCycle][Motion] Parsed Motion List mit {len(motion_list)} Einträgen")
                            except Exception:
                                print("[MasterCycle][Motion] Fehler beim Parsen von motion_list (string)")
                                motion_list = None
                        elif isinstance(raw_motion, dict):
                            motion_list = [raw_motion]
                        elif isinstance(raw_motion, (list, tuple)):
                            motion_list = list(raw_motion)

                    if not motion_list:
                        print("[MasterCycle][Motion] Keine gültige motion_list gefunden → Abbruch")
                        return {'CANCELLED'}

                    # --- Threshold-Aggregation ---
                    print("[MasterCycle][Motion] Aggregiere Threshold-Werte ...")
                    thresholds = {
                        "rot_thresh_x": [], "rot_thresh_y": [],
                        "scale_thresh_min": [], "scale_thresh_max": [],
                        "rot_scale_thresh_rot": [], "rot_scale_thresh_scale": [],
                        "perspective_thresh": []
                    }

                    for entry in motion_list:
                        if not isinstance(entry, dict):
                            continue
                        for k in thresholds.keys():
                            v = entry.get(k)
                            if isinstance(v, (float, int)) and v < 1.0:
                                thresholds[k].append(float(v))

                    # --- Durchschnittsbildung ---
                    motion_value = {}
                    for k, vals in thresholds.items():
                        if vals:
                            motion_value[k] = round(sum(vals) / len(vals), 6)
                            print(f"[MasterCycle][Motion] {k}: {motion_value[k]} (avg aus {len(vals)} Werten)")
                        else:
                            # Wenn nach Aussortieren von 1.0 keine Werte übrig bleiben,
                            # auf 1.0 (neutral) setzen statt 0.0.
                            print(f"[MasterCycle][Motion] {k}: keine Werte → setze auf 1.0")
                            motion_value[k] = 1.0

                    scene["motion_value"] = motion_value
                    print(f"[MasterCycle][Motion] motion_value geschrieben: {motion_value}")

                # ===================================================================
                # Werte in Szenen-Properties schreiben
                # ===================================================================
                print("[MasterCycle][Motion] Übertrage Thresholds in Scene Properties ...")
                for k, prop in {
                    "rot_thresh_x": "kaiserlich_rot_thresh_x",
                    "rot_thresh_y": "kaiserlich_rot_thresh_y",
                    "scale_thresh_min": "kaiserlich_scale_thresh_min",
                    "scale_thresh_max": "kaiserlich_scale_thresh_max",
                    "rot_scale_thresh_rot": "kaiserlich_rot_scale_thresh_rot",
                    "rot_scale_thresh_scale": "kaiserlich_rot_scale_thresh_scale",
                    "perspective_thresh": "kaiserlich_perspective_thresh",
                }.items():
                    if hasattr(scene, prop):
                        try:
                            value = motion_value.get(k, 1.0)  # Default konsistent zu motion_value
                            setattr(scene, prop, value)
                            print(f"[MasterCycle][Motion] {prop} = {value}")
                        except Exception as e:
                            print(f"[MasterCycle][Motion] Fehler beim Setzen von {prop}: {e}")
                            pass
                print("[MasterCycle][Motion] Motion-Phase abgeschlossen → Operator CANCELLED (kein Weak Frame)")
                print("[MasterCycle][Motion] Kein Weak Frame – Übergabe an master_resolve_operator ...")
                try:
                    self._rebuild_good_tracks(context, reason="Post-motion phase handover to resolve")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    print("[MasterCycle][Motion] Übergabe erfolgreich ausgeführt → Prozess abgeschlossen.")
                    return {'FINISHED'}
                except Exception as ex:
                    print(f"[MasterCycle][Motion] FEHLER bei Übergabe an master_resolve_operator: {ex}")
                    return {'CANCELLED'}
            except Exception as e:
                print(f"[MasterCycle][Motion] FEHLER: {e}")
                return {'CANCELLED'}

        # ===================================================================
        # Weiterer Ablauf (wie zuvor)
        # ===================================================================
        if frame is None:
            print("[MasterCycle][Filter] Kein Weak Frame – starte Cleanup-Filterungen")
            try:
                window, area, region, space = find_clip_editor_area(
                    getattr(getattr(context, "space_data", None), "clip", None)
                )

                if not all((window, area, region, space)):
                    raise RuntimeError("No CLIP_EDITOR area found – cannot continue cleanup")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)
                if getattr(space, "clip", None) is None and clip_ref:
                    space.clip = clip_ref

                clip_obj = getattr(space, "clip", None)
                if not clip_obj:
                    raise RuntimeError("No active clip in current context")

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        delete_tracks_by_names(bpy.context, flagged_names)

                self._rebuild_good_tracks(context, reason="Post-Stage1 cleanup")

                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    filter_problematic_tracks(context, threshold=10.0)

                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                frame = find_first_weak_frame(context)
                if frame is None:
                    print("[MasterCycle][Filter] Kein neuer Weak Frame gefunden → starte Resolve Operator")
                    self._rebuild_good_tracks(context, reason="Pre-resolve cleanup checkpoint")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                update_default_sizes(context)
                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
                        print(f"[MasterCycle][Filter] Entferne Cache Key: {k}")
                        del scene[k]

                self._rebuild_good_tracks(context, reason="Post-cache-reset cleanup")

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
            except Exception as ex:
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                print(f"[MasterCycle][Filter] FEHLER: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # Frame setzen + Folgeoperator starten
        # ------------------------------------------------------------------
        print(f"[MasterCycle][NextOp] Setze Frame auf {frame}")
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # ---------------------------------------------------------------
        # Good Tracks erst nach vollständigem Cleanup erzeugen
        # ---------------------------------------------------------------
        try:
            print("[MasterCycle][Tracks] Prüfe ob Cleanup abgeschlossen ist ...")

            # ------------------------------------------------------------
            # Prüfen, ob ein Cleanup durch 'filter_and_delete_all_tracks'
            # bereits ausgeführt wurde (Flag = 'filter_all')
            # ------------------------------------------------------------
            cleanup_stage = scene.get("cleanup_stage", "")
            cleanup_done = cleanup_stage == "filter_all"

            if cleanup_done:
                print(f"[MasterCycle][Tracks] Cleanup vollständig abgeschlossen (Stage={cleanup_stage}) → Erstelle Good Tracks ...")
                self._rebuild_good_tracks(context, reason="Post-cleanup (filter_all) good_tracks rebuild")

                # Nach erfolgreichem Rebuild Flag zurücksetzen, um Wiederholungen zu vermeiden
                if "cleanup_stage" in scene:
                    del scene["cleanup_stage"]
            else:
                print(f"[MasterCycle][Tracks] Kein vollständiger Cleanup erkannt (Stage={cleanup_stage}) → Good Tracks werden NICHT erzeugt")

        except Exception as e:
            print(f"[MasterCycle][Tracks] FEHLER beim Prüfen oder Erstellen der Good Tracks: {e}")

        try:
            motion_value_exists = scene.get("motion_value") is not None
            print(f"[MasterCycle][NextOp] motion_value vorhanden: {motion_value_exists}")
            if motion_value_exists:
                print("[MasterCycle][NextOp] Starte master_detect_adapt Operator")
                bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
            else:
                print("[MasterCycle][NextOp] Starte master_deep_test_operator Operator")
                bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'WARNING'}, f"Error launching next operator: {ex}")
            print(f"[MasterCycle][NextOp] WARNUNG: {ex}")

        print("[MasterCycle] --- Prozess abgeschlossen ---")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)