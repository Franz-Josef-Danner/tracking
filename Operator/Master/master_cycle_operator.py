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
        except Exception:
            pass

        # ===============================================================
        # Low Marker Frame immer suchen – unabhängig von motion_value
        # ===============================================================
        frame = find_first_weak_frame(context)

        # ===============================================================
        # Motion-/Threshold-Logik
        # ===============================================================
        motion_exists = "motion_value" in scene
        if not motion_exists and "motion_list" in scene:
            import ast, statistics
            try:
                ml_raw = scene["motion_list"]
                ml = ast.literal_eval(ml_raw) if isinstance(ml_raw, str) else ml_raw
                if isinstance(ml, dict):
                    result = {}
                    for k, v in ml.items():
                        if isinstance(v, (int, float)) and v < 1.0:
                            result.setdefault(k.split("_")[0], []).append(v)
                    avg_values = {k: round(statistics.mean(vals), 6) for k, vals in result.items() if vals}
                    if avg_values:
                        scene["motion_value"] = avg_values
                # kein else: still valid, aber ohne Erstellung
            except Exception:
                pass

        # ===============================================================
        # Playhead setzen (immer, wenn Frame gefunden)
        # ===============================================================
        if frame is not None:
            scene.frame_current = frame
            try:
                space = getattr(context, "space_data", None)
                if space and getattr(space, "clip_user", None):
                    space.clip_user.frame_current = frame
            except Exception:
                pass

        # ===============================================================
        # Rebuild & Defaults (immer)
        # ===============================================================
        self._rebuild_good_tracks(context, reason="Normal path (weak frame found)")
        update_default_sizes(context)

        # ===============================================================
        # Entscheidungslogik: DeepTest nur wenn KEIN motion_value existiert
        # ===============================================================
        if "motion_value" in scene:
            # motion_value existiert → DeepTest überspringen, direkt Detect Adapt
            try:
                bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
            except Exception:
                pass
            return {'FINISHED'}
        else:
            # Kein motion_value → DeepTest normal starten
            try:
                bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
            except Exception:
                pass
            return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
