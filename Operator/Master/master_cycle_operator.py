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
# Log-Utilities
# ===================================================================

def _log_clip_sources(context: Context):
    clip_from_space = getattr(getattr(context, "space_data", None), "clip", None)
    clip_from_edit  = getattr(context, "edit_movieclip", None)
    clip_from_trk   = getattr(getattr(context.scene, "tracking", None), "active", None)
    print("[LOG][CLIP CHECK] space:", getattr(clip_from_space, "name", None))
    print("[LOG][CLIP CHECK] edit :", getattr(clip_from_edit,  "name", None))
    print("[LOG][CLIP CHECK] trk  :", getattr(clip_from_trk,   "name", None))
    return clip_from_space or clip_from_edit or clip_from_trk


def _safe_eval_uuid_map(s: str) -> dict:
    """Robuste Auswertung des als String gespeicherten Dicts {uuid: name}."""
    try:
        import ast
        d = ast.literal_eval(s)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def _log_scene_strings(scene: bpy.types.Scene, key: str):
    uuids = list(scene.get(key, []))
    names = list(scene.get(f"{key}_names", []))
    uuid_map_raw = scene.get(f"{key}_uuid_map", "")
    uuid_map = _safe_eval_uuid_map(uuid_map_raw) if isinstance(uuid_map_raw, str) else (uuid_map_raw or {})

    print(f"[LOG][SCENE STR] Key='{key}' | UUIDs: {len(uuids)} | Names: {len(names)} | Map: {len(uuid_map)}")
    if names:
        print(f"[LOG][SCENE STR] Beispiele Names (bis 10): {names[:10]}")
    if uuids:
        print(f"[LOG][SCENE STR] Beispiele UUIDs (bis 10): {uuids[:10]}")

    # Konsistenzhinweise
    if len(uuids) != len(names):
        print(f"[LOG][WARN] Mismatch Längen: UUIDs={len(uuids)} vs Names={len(names)}")
    if uuid_map and len(uuid_map) != len(uuids):
        print(f"[LOG][WARN] Map/UUID mismatch: Map={len(uuid_map)} vs UUIDs={len(uuids)}")

    return uuids, names, uuid_map


def _log_scene_clip_tracks(clip) -> list:
    if not clip or not hasattr(clip, "tracking"):
        print("[LOG][CLIP TRACKS] Kein Clip/Tracking verfügbar.")
        return []
    tracks = list(clip.tracking.tracks)
    print(f"[LOG][CLIP TRACKS] Clip='{clip.name}' | Anzahl Tracks: {len(tracks)}")
    if tracks:
        ex = [t.name for t in tracks[:10]]
        print(f"[LOG][CLIP TRACKS] Beispiele (bis 10): {ex}")
    return tracks


def _compare_strings_vs_scene(scene: bpy.types.Scene, clip, key: str):
    """Vergleicht die im Scene-String abgelegten Track-Namen mit den aktuell im Clip existierenden Tracks."""
    print(f"[LOG][COMPARE] ---- Start Vergleich '{key}' ----")
    uuids, names, uuid_map = _log_scene_strings(scene, key)
    tracks = _log_scene_clip_tracks(clip)

    scene_names_set = set(names)
    scene_map_names_set = set(uuid_map.values()) if uuid_map else set()
    current_names_set = set(t.name for t in tracks)

    # Primär vergleichen wir die Name-Liste; Map ist Zusatz-Check
    missing_in_scene = sorted(list(scene_names_set - current_names_set))
    extra_in_scene   = sorted(list(current_names_set - scene_names_set))

    print(f"[LOG][COMPARE] Übereinstimmungen: {len(scene_names_set & current_names_set)}")
    print(f"[LOG][COMPARE] Fehlend in Szene (in String, aber nicht im Clip): {len(missing_in_scene)}")
    if missing_in_scene:
        print(f"[LOG][COMPARE] -> Beispiele fehlend (bis 20): {missing_in_scene[:20]}")

    print(f"[LOG][COMPARE] Extra in Szene (im Clip, aber nicht im String): {len(extra_in_scene)}")
    if extra_in_scene:
        print(f"[LOG][COMPARE] -> Beispiele extra (bis 20): {extra_in_scene[:20]}")

    # Zusatz: Abgleich Map (falls vorhanden)
    if scene_map_names_set:
        map_missing_in_scene = sorted(list(scene_map_names_set - current_names_set))
        map_extra_in_scene   = sorted(list(current_names_set - scene_map_names_set))
        print(f"[LOG][COMPARE][MAP] Übereinstimmungen (Map vs Clip): {len(scene_map_names_set & current_names_set)}")
        print(f"[LOG][COMPARE][MAP] Fehlend in Szene: {len(map_missing_in_scene)}")
        if map_missing_in_scene:
            print(f"[LOG][COMPARE][MAP] -> Beispiele fehlend (bis 20): {map_missing_in_scene[:20]}")
        print(f"[LOG][COMPARE][MAP] Extra in Szene: {len(map_extra_in_scene)}")
        if map_extra_in_scene:
            print(f"[LOG][COMPARE][MAP] -> Beispiele extra (bis 20): {map_extra_in_scene[:20]}")

    print(f"[LOG][COMPARE] ---- Ende Vergleich '{key}' ----")


# ===================================================================
# Zentrale Hilfsfunktion: UUID-basierte Track-Speicherung in Scene
# ===================================================================

def store_tracks_in_scene(scene, context, key="good_tracks"):
    """
    Erfasst alle Tracks des aktiven Clips, vergibt frische UUIDs und
    speichert Name-Liste + UUID-Liste + UUID→Name Map in Scene-Strings.
    Vorher werden good/best-Strings sauber entfernt.
    """
    # Clip ermitteln
    clip = None
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        clip = space.clip
    if not clip:
        clip = getattr(getattr(context, "scene", None), "tracking", None)
        clip = getattr(clip, "active", None) if clip else None
    if not clip:
        print("[LOG][STORE] Kein aktiver Clip gefunden – Abbruch.")
        return

    tracking = clip.tracking
    all_tracks = list(tracking.tracks)
    print(f"[LOG][STORE] Ziel-Key='{key}' | Clip='{clip.name}' | Tracks: {len(all_tracks)}")

    # Bestehende Scene-Strings bereinigen
    for k in (
        "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
        "best_tracks", "best_tracks_names", "best_tracks_uuid_map"
    ):
        if k in scene:
            del scene[k]
            print(f"[LOG][STORE] Entfernt Scene-String: {k}")

    # Neu aufbauen
    uuid_list, name_list, uuid_map = [], [], {}
    for t in all_tracks:
        uid = str(uuid.uuid4())
        uuid_list.append(uid)
        name_list.append(t.name)
        uuid_map[uid] = t.name

    scene[key] = uuid_list
    scene[f"{key}_names"] = name_list
    scene[f"{key}_uuid_map"] = str(uuid_map)

    print(f"[LOG][STORE] Gespeichert unter '{key}': UUIDs={len(uuid_list)}, Names={len(name_list)}, Map={len(uuid_map)}")
    if name_list:
        print(f"[LOG][STORE] Beispiele Names (bis 10): {name_list[:10]}")


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
    # Interner Helper: Erzwingt einen Refresh des Clip-Kontexts
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # String neu aufbauen + Logging & Vergleich
    # ------------------------------------------------------------
    def _rebuild_and_log(self, context: Context, key: str, reason: str = ""):
        scene = context.scene
        clip = _log_clip_sources(context)
        if not clip or not hasattr(clip, "tracking"):
            print(f"[LOG][REBUILD] Kein Clip/Tracking – skip. Reason: {reason}")
            return

        self._force_clip_refresh(context, clip)
        print(f"[LOG][REBUILD] Rebuild '{key}' – Reason: {reason}")
        store_tracks_in_scene(scene, context, key=key)
        _compare_strings_vs_scene(scene, clip, key)

    def _rebuild_good_tracks(self, context: Context, reason: str = ""):
        self._rebuild_and_log(context, key="good_tracks", reason=reason)

    # ------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------
    def execute(self, context: Context):
        scene = context.scene
        print("[LOG][EXEC] Master Cycle start")
        frame = find_first_weak_frame(context)
        print(f"[LOG][EXEC] find_first_weak_frame -> {frame}")

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

                # Stage 1: Blender-eigenes Filter
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.clip.filter_tracks(track_threshold=30.0)
                    tracking = clip_obj.tracking
                    flagged_names = [t.name for t in tracking.tracks if t.select]
                    print(f"[LOG][EXEC] Stage1 flagged names: {len(flagged_names)}")
                    if flagged_names:
                        from ...Helper.delete import delete_tracks_by_names
                        delete_tracks_by_names(bpy.context, flagged_names)

                self._rebuild_good_tracks(context, reason="Post-Stage1 cleanup")

                # Stage 2: Eigene Problem-Filter
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    filter_problematic_tracks(context, threshold=10.0)

                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                # Re-Check auf weak frame
                frame = find_first_weak_frame(context)
                print(f"[LOG][EXEC] Recheck weak frame -> {frame}")
                if frame is None:
                    self._rebuild_and_log(context, key="good_tracks", reason="Pre-resolve cleanup checkpoint")
                    print("[LOG][EXEC] Übergabe an Resolve")
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                # Defaults + Cache-Reset
                update_default_sizes(context)
                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
                        del scene[k]
                        print(f"[LOG][EXEC] Cache gelöscht: {k}")

                self._rebuild_good_tracks(context, reason="Post-cache-reset cleanup")

                # Szenen-Properties baseline (defensiv)
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
                print(f"[LOG][ERROR] {ex}")
                return {'CANCELLED'}

        # Playhead setzen
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # Rebuild + Vergleich (Normalpfad)
        self._rebuild_good_tracks(context, reason="Normal path (weak frame found)")

        # Optional: vor Übergabe bereits Vergleich auch für best_tracks anzeigen, falls existiert
        clip = _log_clip_sources(context)
        if "best_tracks" in scene and clip:
            _compare_strings_vs_scene(scene, clip, "best_tracks")

        # Handover
        try:
            print("[LOG][EXEC] Übergabe an Deep Test")
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            print(f"[LOG][WARN] Deep Test Start fehlgeschlagen: {ex}")

        print("[LOG][EXEC] Master Cycle finished")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
