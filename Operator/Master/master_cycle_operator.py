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
        # ===================================================================
        # Zusätzliche Motion-List-Verarbeitung beim ersten None-Ergebnis
        # ===================================================================
        if frame is None:
            try:
                # ---------------------------------------------------------------
                # Prüfen, ob motion_value bereits existiert → direkte Übernahme
                # ---------------------------------------------------------------
                existing_motion_value = scene.get("motion_value")
                if existing_motion_value and isinstance(existing_motion_value, dict):
                    motion_value = existing_motion_value
                else:
                    motion_list = scene.get("motion_list")
                    if motion_list and isinstance(motion_list, (list, tuple)):
                        thresholds = {
                            "rot_thresh_x": [],
                            "rot_thresh_y": [],
                            "scale_thresh_min": [],
                            "scale_thresh_max": [],
                            "rot_scale_thresh_rot": [],
                            "rot_scale_thresh_scale": [],
                            "perspective_thresh": []
                        }

                        for entry in motion_list:
                            if not isinstance(entry, dict):
                                continue
                            # Prüfen, ob Threshold komplett ausgelassen werden soll (wenn immer 1)
                            for k in list(thresholds.keys()):
                                v = entry.get(k)
                                # Wenn der Threshold-Wert exakt 1 ist → komplett überspringen
                                if isinstance(v, (float, int)) and v == 1.0:
                                    thresholds.pop(k, None)
                                    continue
                                # Nur Werte kleiner als 1 berücksichtigen
                                if isinstance(v, (float, int)) and v < 1.0:
                                    thresholds.setdefault(k, []).append(float(v))

                        # Falls bestimmte Keys ausgelassen wurden, sicherstellen, dass sie nicht fehlen
                        all_keys = {
                            "rot_thresh_x", "rot_thresh_y",
                            "scale_thresh_min", "scale_thresh_max",
                            "rot_scale_thresh_rot", "rot_scale_thresh_scale",
                            "perspective_thresh"
                        }
                        for key in all_keys:
                            if key not in thresholds:
                                thresholds[key] = []

                        # ---------------------------------------------------------------
                        # Debug-Ausgabe des Berechnungsvorgangs
                        # ---------------------------------------------------------------
                        print("\n[MOTION LIST → MOTION VALUE] ----------------------------")
                        for k, vals in thresholds.items():
                            if vals:
                                print(f"  {k}: {len(vals)} Werte  |  min={min(vals):.6f}, max={max(vals):.6f}, avg={sum(vals)/len(vals):.6f}")
                            else:
                                print(f"  {k}: Keine gültigen Werte (<1) gefunden oder ausgelassen.")
                        print("-------------------------------------------------------------")

                        motion_value = {}
                        for k, vals in thresholds.items():
                            if vals:
                                motion_value[k] = round(sum(vals) / len(vals), 6)
                            else:
                                motion_value[k] = 0.0

                        scene["motion_value"] = motion_value

                        # ---------------------------------------------------------------
                        # Ergebnis-Ausgabe von motion_value
                        # ---------------------------------------------------------------
                        print("[RESULT] scene['motion_value'] =", motion_value)
                # ---------------------------------------------------------------
                # motion_value (egal ob neu oder vorhanden) in Szene übertragen
                # ---------------------------------------------------------------
                try:
                    if "kaiserlich_rot_thresh_x" in scene:
                        scene.kaiserlich_rot_thresh_x = motion_value.get("rot_thresh_x", 0.0)
                    if "kaiserlich_rot_thresh_y" in scene:
                        scene.kaiserlich_rot_thresh_y = motion_value.get("rot_thresh_y", 0.0)
                    if "kaiserlich_scale_thresh_min" in scene:
                        scene.kaiserlich_scale_thresh_min = motion_value.get("scale_thresh_min", 0.0)
                    if "kaiserlich_scale_thresh_max" in scene:
                        scene.kaiserlich_scale_thresh_max = motion_value.get("scale_thresh_max", 0.0)
                    if "kaiserlich_rot_scale_thresh_rot" in scene:
                        scene.kaiserlich_rot_scale_thresh_rot = motion_value.get("rot_scale_thresh_rot", 0.0)
                    if "kaiserlich_rot_scale_thresh_scale" in scene:
                        scene.kaiserlich_rot_scale_thresh_scale = motion_value.get("rot_scale_thresh_scale", 0.0)
                    if "kaiserlich_perspective_thresh" in scene:
                        scene.kaiserlich_perspective_thresh = motion_value.get("perspective_thresh", 0.0)

                    # UI-Redraw auslösen
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.type == 'CLIP_EDITOR':
                                area.tag_redraw()
                except Exception:
                    pass
                    thresholds = {
                        "rot_thresh_x": [],
                        "rot_thresh_y": [],
                        "scale_thresh_min": [],
                        "scale_thresh_max": [],
                        "rot_scale_thresh_rot": [],
                        "rot_scale_thresh_scale": [],
                        "perspective_thresh": []
                    }

                    for entry in motion_list:
                        if not isinstance(entry, dict):
                            continue
                        for k in thresholds.keys():
                            v = entry.get(k)
                            if isinstance(v, (float, int)) and v < 1.0:
                                thresholds[k].append(float(v))

                    motion_value = {}
                    for k, vals in thresholds.items():
                        if vals:
                            motion_value[k] = round(sum(vals) / len(vals), 6)
                        else:
                            motion_value[k] = 0.0

                    scene["motion_value"] = motion_value

                    # Werte aus motion_value direkt in Szenen-Properties übertragen
                    try:
                        if "kaiserlich_rot_thresh_x" in scene:
                            scene.kaiserlich_rot_thresh_x = motion_value.get("rot_thresh_x", 0.0)
                        if "kaiserlich_rot_thresh_y" in scene:
                            scene.kaiserlich_rot_thresh_y = motion_value.get("rot_thresh_y", 0.0)
                        if "kaiserlich_scale_thresh_min" in scene:
                            scene.kaiserlich_scale_thresh_min = motion_value.get("scale_thresh_min", 0.0)
                        if "kaiserlich_scale_thresh_max" in scene:
                            scene.kaiserlich_scale_thresh_max = motion_value.get("scale_thresh_max", 0.0)
                        if "kaiserlich_rot_scale_thresh_rot" in scene:
                            scene.kaiserlich_rot_scale_thresh_rot = motion_value.get("rot_scale_thresh_rot", 0.0)
                        if "kaiserlich_rot_scale_thresh_scale" in scene:
                            scene.kaiserlich_rot_scale_thresh_scale = motion_value.get("rot_scale_thresh_scale", 0.0)
                        if "kaiserlich_perspective_thresh" in scene:
                            scene.kaiserlich_perspective_thresh = motion_value.get("perspective_thresh", 0.0)

                        # UI-Redraw auslösen, damit Änderungen sofort sichtbar werden
                        for window in bpy.context.window_manager.windows:
                            for area in window.screen.areas:
                                if area.type == 'CLIP_EDITOR':
                                    area.tag_redraw()
                    except Exception:
                        pass
            except Exception as ex:
                self.report({'ERROR'}, f"Motion list processing failed: {ex}")

        if frame is None:
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
            # Wenn motion_value existiert → Detect Adapt starten, sonst Deep Test
            motion_value_exists = scene.get("motion_value") is not None
            if motion_value_exists:
                try:
                    bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                except Exception as e:
                    self.report({'WARNING'}, f"Fallback to Deep Test due to Detect Adapt error: {e}")
                    bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
            else:
                bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'WARNING'}, f"Error launching next operator: {ex}")

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
