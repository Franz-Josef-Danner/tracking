import bpy
import uuid
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

    def _force_clip_refresh(self, context: Context, clip) -> None:
        window, area, region, space = None, None, None, None
        try:
            window, area, region, space = find_clip_editor_area(
                getattr(getattr(context, "space_data", None), "clip", None) or clip
            )
        except Exception:
            pass

        try:
            if space:
                space.clip = clip
        except Exception:
            pass

        try:
            context.view_layer.update()
        except Exception:
            pass

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
        except Exception:
            pass

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.clip.select_all(action='DESELECT')
        except Exception:
            pass

    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        scene = context.scene
        clip_from_space = getattr(getattr(context, "space_data", None), "clip", None)
        clip_from_edit = getattr(context, "edit_movieclip", None)
        clip_from_tracking = getattr(getattr(context.scene, "tracking", None), "active", None)

        clip = clip_from_space or clip_from_edit or clip_from_tracking
        if not clip or not hasattr(clip, "tracking"):
            return

        self._force_clip_refresh(context, clip)
        store_tracks_in_scene(scene, context, key="good_tracks")

    def execute(self, context: Context):
        scene = context.scene

        # ===============================================================
        # Vollständige Scene-Bereinigung beim Auslösen des Operators
        # ===============================================================
        # Entfernt sämtliche gespeicherten Track-Strings inkl. Varianten
        # (UUID-Maps, Namenslisten, Kalibrierungsdaten usw.).
        # Dadurch wird sichergestellt, dass keine alten Datenreste
        # aus vorigen Tracking-Zyklen verwendet werden.
        try:
            keys_to_delete = [
                "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
                "best_tracks", "best_tracks_names", "best_tracks_uuid_map",
                "calibrate_tracks", "calibrate_tracks_names", "calibrate_tracks_uuid_map",
                "frame_value_cache", "kaiserlich_best_thresholds"
            ]

            for _k in keys_to_delete:
                if _k in scene:
                    del scene[_k]

        except Exception as ex:
            pass

        frame = find_first_weak_frame(context)

        if frame is None:
            # ============================================================
            # Kein Low Marker Frame gefunden → Threshold-Auswertung
            # ============================================================
            scene = context.scene

            # 1) Wenn motion_value bereits existiert, DeepTest überspringen
            if "motion_value" in scene:
                print("[MASTER CYCLE] Motion value bereits vorhanden → DeepTest übersprungen.")
                mv = scene["motion_value"]
                if isinstance(mv, dict):
                    # Werte direkt in Szene eintragen
                    scene["kaiserlich_rot_thresh_x"] = mv.get("rot_thresh_x", 1.0)
                    scene["kaiserlich_rot_thresh_y"] = mv.get("rot_thresh_y", 1.0)
                    scene["kaiserlich_scale_thresh_min"] = mv.get("scale_thresh_min", 1.0)
                    scene["kaiserlich_scale_thresh_max"] = mv.get("scale_thresh_max", 1.1)
                    scene["kaiserlich_rot_scale_thresh_rot"] = mv.get("rot_scale_thresh_rot", 1.0)
                    scene["kaiserlich_rot_scale_thresh_scale"] = mv.get("rot_scale_thresh_scale", 1.0)
                    scene["kaiserlich_perspective_thresh"] = mv.get("perspective_thresh", 1.0)
                else:
                    print("[MASTER CYCLE][WARN] motion_value ist kein Dictionary – ignoriert.")

                # Direkt an master_detect_adapt weitergeben
                try:
                    bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                except Exception as e:
                    print(f"[MASTER CYCLE][ERROR] Detect Adapt Übergabe fehlgeschlagen: {e}")
                return {'FINISHED'}

            # 2) Wenn keine motion_value vorhanden → motion_list auswerten
            if "motion_list" in scene:
                import ast, statistics
                try:
                    ml_raw = scene["motion_list"]
                    ml = ast.literal_eval(ml_raw) if isinstance(ml_raw, str) else ml_raw
                    if isinstance(ml, dict):
                        result = {}
                        for k, v in ml.items():
                            if isinstance(v, (int, float)):
                                if v < 1.0:
                                    result.setdefault(k.split("_")[0], []).append(v)

                        # Mittelwerte berechnen für jeden Threshold-Typ
                        avg_values = {}
                        for k, vals in result.items():
                            if vals:
                                avg_values[k] = round(statistics.mean(vals), 6)

                        # motion_value speichern
                        scene["motion_value"] = avg_values
                        print(f"[MASTER CYCLE] motion_value erstellt: {avg_values}")
                    else:
                        print("[MASTER CYCLE][WARN] motion_list ist kein Dictionary – ignoriert.")
                except Exception as e:
                    print(f"[MASTER CYCLE][ERROR] motion_list konnte nicht ausgewertet werden: {e}")

                # Falls motion_value nun existiert, direkt weitergeben
                if "motion_value" in scene:
                    try:
                        bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                    except Exception as e:
                        print(f"[MASTER CYCLE][ERROR] Übergabe an Detect Adapt fehlgeschlagen: {e}")
                    return {'FINISHED'}

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
                    self._rebuild_good_tracks(context, reason="Pre-resolve cleanup checkpoint")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                update_default_sizes(context)
                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
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
                return {'CANCELLED'}

        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        self._rebuild_good_tracks(context, reason="Normal path (weak frame found)")

        try:
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception:
            pass

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
