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
    """
    Erfasst alle Tracks des aktiven Clips, generiert persistente UUIDs
    und speichert sie im Scene-Storage (keine IDProperties!).
    Löscht vorab alle vorhandenen good/best-Einträge, um Konflikte zu vermeiden.
    """
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    if not clip:
        clip = getattr(context.scene.tracking, "active", None)
    if not clip:
        print("[store_tracks_in_scene] ❌ Kein aktiver Clip gefunden.")
        return

    tracking = clip.tracking
    all_tracks = list(tracking.tracks)
    print(f"[store_tracks_in_scene] Clip '{clip.name}' – {len(all_tracks)} Tracks erfasst")

    # ------------------------------------------------------------
    # Alte Scene-Keys entfernen (good_* und best_*)
    # ------------------------------------------------------------
    for k in (
        "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
        "best_tracks", "best_tracks_names", "best_tracks_uuid_map"
    ):
        if k in scene:
            del scene[k]
    print("[store_tracks_in_scene] Alte Scene-Keys (good/best) bereinigt.")

    # ------------------------------------------------------------
    # Neue UUID-Listen generieren
    # ------------------------------------------------------------
    uuid_list, name_list, uuid_map = [], [], {}

    # Statt IDProperties: zentrale Mapping-Struktur im Scene-Storage
    for t in all_tracks:
        uid = str(uuid.uuid4())
        uuid_list.append(uid)
        name_list.append(t.name)
        uuid_map[uid] = t.name  # UUID → Trackname

    scene[key] = uuid_list
    scene[f"{key}_names"] = name_list
    scene[f"{key}_uuid_map"] = str(uuid_map)  # als String gespeichert (dict nicht erlaubt)

    print(f"[store_tracks_in_scene] Gespeichert: {len(uuid_list)} UUIDs, {len(name_list)} Namen")
    print(f"[store_tracks_in_scene] Beispiele UUIDs: {uuid_list[:5]}")


# ===================================================================
# Haupt-Operator
# ===================================================================

class KAISERLICHTRACKER_OT_master_cycle_operator(Operator):
    """Master Operator – Sets the playhead to the frame with the fewest active markers"""
    bl_idname = "kaiserlich_tracker.master_cycle_operator"
    bl_label = "Master Operator"
    bl_description = "Sets the playhead to the first frame with the lowest number of active markers"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------
    # Interner Helper: Erzwingt Refresh des Clip-Kontexts
    # ------------------------------------------------------------
    def _force_clip_refresh(self, context: Context, clip) -> None:
        window, area, region, space = None, None, None, None
        try:
            window, area, region, space = find_clip_editor_area(
                getattr(getattr(context, "space_data", None), "clip", None) or clip
            )
            print(f"[MASTER CYCLE][REFRESH] find_clip_editor_area -> "
                  f"window={bool(window)}, area={bool(area)}, region={bool(region)}, space={bool(space)}")
        except Exception as e:
            print(f"[MASTER CYCLE][REFRESH] WARNING find_clip_editor_area: {e}")

        try:
            if space:
                space.clip = clip
                print("[MASTER CYCLE][REFRESH] space.clip re-bound to active clip")
        except Exception as e:
            print(f"[MASTER CYCLE][REFRESH] WARNING rebind space.clip: {e}")

        try:
            context.view_layer.update()
            print("[MASTER CYCLE][REFRESH] view_layer.update() done")
        except Exception as e:
            print(f"[MASTER CYCLE][REFRESH] WARNING view_layer.update: {e}")

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
                print("[MASTER CYCLE][REFRESH] redraw_timer executed")
        except Exception as e:
            print(f"[MASTER CYCLE][REFRESH] WARNING redraw_timer: {e}")

        try:
            if all((window, area, region, space)):
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.clip.select_all(action='DESELECT')
                print("[MASTER CYCLE][REFRESH] clip.select_all(DESELECT) executed")
        except Exception as e:
            print(f"[MASTER CYCLE][REFRESH] WARNING select_all: {e}")

    # ------------------------------------------------------------
    # Lokaler Helper: Rebuild good_tracks via store_tracks_in_scene
    # ------------------------------------------------------------
    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        print(f"[MASTER CYCLE] --- Rebuild good_tracks START ({reason}) ---")
        scene = context.scene

        clip_from_space = getattr(getattr(context, "space_data", None), "clip", None)
        clip_from_edit = getattr(context, "edit_movieclip", None)
        clip_from_tracking = getattr(getattr(context.scene, "tracking", None), "active", None)

        print(f"[MASTER CYCLE][CLIP CHECK] clip_from_space:   {clip_from_space.name if clip_from_space else None}")
        print(f"[MASTER CYCLE][CLIP CHECK] clip_from_edit:    {clip_from_edit.name if clip_from_edit else None}")
        print(f"[MASTER CYCLE][CLIP CHECK] clip_from_tracking: {getattr(clip_from_tracking, 'name', None) if clip_from_tracking else None}")

        clip = clip_from_space or clip_from_edit or clip_from_tracking
        if not clip or not hasattr(clip, "tracking"):
            print("[MASTER CYCLE] ❌ Kein gültiger Clip gefunden – Abbruch des Rebuilds")
            return

        self._force_clip_refresh(context, clip)

        print(f"[MASTER CYCLE] Aktiver Clip: {clip.name} (id={id(clip)})")
        print(f"[MASTER CYCLE] Anzahl Tracks laut Clip: {len(list(clip.tracking.tracks))}")

        # ✅ Persistente Speicherung (UUID-basiert)
        store_tracks_in_scene(scene, context, key="good_tracks")

        print(f"[MASTER CYCLE] Scene keys after rebuild: {list(scene.keys())}")
        print(f"[MASTER CYCLE] --- Rebuild good_tracks END ---")

    # ------------------------------------------------------------
    # Hauptausführung
    # ------------------------------------------------------------
    def execute(self, context: Context):
        print("\n[MASTER CYCLE] --------------------------------------------")
        print("[MASTER CYCLE] Operator started")

        scene = context.scene
        print(f"[MASTER CYCLE] Scene frame_current before find: {scene.frame_current}")
        frame = find_first_weak_frame(context)
        print(f"[MASTER CYCLE] find_first_weak_frame result: {frame}")

        # ------------------------------------------------------------------
        # CLEANUP-ZWEIG
        # ------------------------------------------------------------------
        if frame is None:
            print("[MASTER CYCLE] No weak frame found – entering CLEANUP branch")

            try:
                print("[MASTER CYCLE] Attempting to find CLIP_EDITOR context ...")
                window, area, region, space = find_clip_editor_area(
                    getattr(getattr(context, "space_data", None), "clip", None)
                )
                print(f"[MASTER CYCLE] find_clip_editor_area returned -> "
                      f"window={bool(window)}, area={bool(area)}, region={bool(region)}, space={bool(space)}")

                if not all((window, area, region, space)):
                    raise RuntimeError("No CLIP_EDITOR area found – cannot continue cleanup")

                clip_ref = getattr(getattr(context, "space_data", None), "clip", None)
                if getattr(space, "clip", None) is None and clip_ref:
                    space.clip = clip_ref
                    print(f"[MASTER CYCLE] Assigned clip_ref to space.clip")

                clip_obj = getattr(space, "clip", None)
                if not clip_obj:
                    raise RuntimeError("No active clip in current context")
                print(f"[MASTER CYCLE] Active clip in context: {clip_obj.name}")

                print("[MASTER CYCLE] Stage 1: filter_tracks (threshold=30.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    res = bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    print(f"[MASTER CYCLE] bpy.ops.clip.filter_tracks result: {res}")
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    print(f"[MASTER CYCLE] Stage 1: {len(flagged_names)} tracks flagged")
                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        delete_tracks_by_names(bpy.context, flagged_names)
                        print("[MASTER CYCLE] Stage 1: flagged tracks deleted")
                    else:
                        print("[MASTER CYCLE] Stage 1: No tracks flagged")

                self._rebuild_good_tracks(context, reason="Post-Stage1 cleanup")

                print("[MASTER CYCLE] Stage 2: filter_problematic_tracks (threshold=10.0)")
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        filter_problematic_tracks(context, threshold=10.0)
                        print("[MASTER CYCLE] Stage 2: filter_problematic_tracks executed")
                    except Exception as e:
                        print(f"[MASTER CYCLE] Stage 2 WARNING: {e}")

                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                print("[MASTER CYCLE] Searching again for weak frame after cleanup...")
                frame = find_first_weak_frame(context)
                print(f"[MASTER CYCLE] New find_first_weak_frame result: {frame}")
                if frame is None:
                    self._rebuild_good_tracks(context, reason="Pre-resolve cleanup checkpoint")
                    print("[MASTER CYCLE] No weak frame after cleanup – starting resolve operator")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    print("[MASTER CYCLE] Resolve triggered, exiting operator")
                    return {'FINISHED'}

                print("[MASTER CYCLE] Stage 3: update_default_sizes + cache reset")
                op, os, np, ns = update_default_sizes(context)
                print(f"[MASTER CYCLE] update_default_sizes returned: op={op}, os={os}, np={np}, ns={ns}")

                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
                        del scene[k]
                        print(f"[MASTER CYCLE] Cleared scene cache: {k}")

                self._rebuild_good_tracks(context, reason="Post-cache-reset cleanup")

                print("[MASTER CYCLE] Resetting scene threshold properties ...")
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
                print("[MASTER CYCLE] Threshold properties reset complete")

            except Exception as ex:
                print(f"[MASTER CYCLE] ERROR during cleanup: {ex}")
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # NORMALZWEIG
        # ------------------------------------------------------------------
        print(f"[MASTER CYCLE] Weak frame found: {frame}")
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
                print(f"[MASTER CYCLE] Set clip_user.frame_current to {frame}")
            else:
                print("[MASTER CYCLE] No clip_user available to set frame")
        except Exception as e:
            print(f"[MASTER CYCLE] ERROR while setting frame_current: {e}")

        self._rebuild_good_tracks(context, reason="Normal path (weak frame found)")

        try:
            print("[MASTER CYCLE] Triggering Deep Test Operator...")
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
            print("[MASTER CYCLE] Deep Test Operator triggered successfully")
        except Exception as e:
            print(f"[MASTER CYCLE] WARNING: Could not trigger Deep Test Operator: {e}")

        print("[MASTER CYCLE] Operator finished successfully")
        print("------------------------------------------------------------\n")
        return {'FINISHED'}


# ---- Registration ----------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
