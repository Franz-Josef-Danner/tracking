# master_cycle_operator.py
import bpy
import uuid
import ast
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ...Helper.low_marker_frame_solve import find_first_weak_frame_solve
from ...Helper.update_default_sizes import update_default_sizes
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.delete import delete_tracks_by_names
from ...Helper.solve_validation import has_solve_basis, get_solve_basis_stats
from ...Helper.bootstrap import run_bootstrap, apply_bootstrap_defaults  # <-- wichtig!

# ===================================================================
# Zentrale Hilfsfunktion: UUID-basierte Track-Speicherung in Scene
# ===================================================================
def store_tracks_in_scene(scene, context, key="good_tracks"):
    log_key = str(key).upper()

    # logging entfernt

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
    # logging entfernt

    # ------------------------------------------------------------
    # Lösche nur die eigenen GOOD_TRACKS Keys, wenn wir GOOD erzeugen
    # ------------------------------------------------------------
    if key == "good_tracks":
        # Vorher-Status loggen
        existing_keys = {}
        for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map"):
            if k in scene:
                existing_keys[k] = scene.get(k)

        if existing_keys:
            msg_parts = []
            for k, v in existing_keys.items():
                length_info = "n/a"
                try:
                    if isinstance(v, (list, tuple)):
                        length_info = len(v)
                    elif isinstance(v, str):
                        length_info = len(v)
                except Exception:
                    pass
                msg_parts.append(f"{k} (len={length_info})")
            # logging entfernt
        else:
            pass

        for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map"):
            if k in scene:
                del scene[k]

        # logging entfernt

    uuid_list, name_list, uuid_map = [], [], {}
    for t in all_tracks:
        uid = str(uuid.uuid4())
        uuid_list.append(uid)
        name_list.append(t.name)
        uuid_map[uid] = t.name

    scene[key] = uuid_list
    scene[f"{key}_names"] = name_list
    scene[f"{key}_uuid_map"] = str(uuid_map)

    # logging entfernt


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
        # logging entfernt

        self._force_clip_refresh(context, clip)
        store_tracks_in_scene(scene, context, key="good_tracks")

        # logging entfernt

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    def execute(self, context: Context):
        scene = context.scene

        # ===============================================================
        # Scene-Bereinigung (alte Daten entfernen)
        # ===============================================================
        try:
            # good_tracks* wurden hier entfernt – jetzt bleiben sie erhalten
            keys_to_delete = [
                "calibrate_tracks", "calibrate_tracks_names", "calibrate_tracks_uuid_map",
                "frame_value_cache", "kaiserlich_best_thresholds"
            ]
            for _k in keys_to_delete:
                if _k in scene:
                    del scene[_k]
        except Exception as e:
            pass

        frame = find_first_weak_frame_solve(context)
        # ================================================================
        # Bootstrap korrekt mit 'ef' (gewünschte Markeranzahl) ausführen
        # ================================================================
        scene = context.scene
        try:
            ef = getattr(scene, "kaiserlich_markers_per_frame", None)
            if ef is None:
                ef = scene.get("kaiserlich_markers_per_frame", 0)
            ef = int(ef) if isinstance(ef, (int, float, str)) else 0
            if ef <= 0:
                ef = 50  # Fallback: 50 Marker Zielwert
        except Exception:
            ef = 50

        run_bootstrap(context, ef)  # <-- ef übergeben!
        apply_bootstrap_defaults(context, scene.get("bootstrap_params", {}))
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "No active clip found.")
            return {"CANCELLED"}
        # ===================================================================
        # Weiterer Ablauf (wie zuvor)
        # ===================================================================
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
                    # Entfernt: automatischer Standard-Filter der Tracks (track_threshold=30.0)

                    tracking = clip_obj.tracking

                    # Mindestanzahl Frames pro Track aus scene.kaiserlich_frames_per_track holen
                    min_frames = 0
                    try:
                        if hasattr(scene, "kaiserlich_frames_per_track"):
                            val = getattr(scene, "kaiserlich_frames_per_track", None)
                        else:
                            val = scene.get("kaiserlich_frames_per_track", None)
                        if isinstance(val, (int, float)) and val > 0:
                            min_frames = int(val)
                    except Exception:
                        pass

                    flagged_names = []
                    deleted_info = []  # (name, active_length)
                    kept_info = []     # (name, active_length)

                    def _is_marker_disabled(track, marker) -> bool:
                        """Kapselt die Logik, wann ein Marker als 'inaktiv' gilt."""
                        # kompletter Track gemutet → alles inaktiv
                        if getattr(track, "mute", False):
                            return True

                        # Marker-spezifisches Mute-Flag (falls vorhanden)
                        if getattr(marker, "mute", False):
                            return True

                        # Custom-ID-Property "disabled" (z. B. aus Add-on-Logik)
                        try:
                            if "disabled" in marker and bool(marker["disabled"]):
                                return True
                        except Exception:
                            pass

                        return False

                    if min_frames > 0:
                        for t in tracking.tracks:
                            try:
                                all_frames = set()
                                active_frames = set()

                                for m in t.markers:
                                    if not hasattr(m, "frame"):
                                        continue

                                    f = m.frame
                                    all_frames.add(f)

                                    # nur wirklich aktive Marker zählen
                                    if _is_marker_disabled(t, m):
                                        continue

                                    active_frames.add(f)

                                active_length = len(active_frames)

                                # Wenn nichts aktiv, wird der Track faktisch als 0 bewertet
                                if active_length < min_frames:
                                    flagged_names.append(t.name)
                                    deleted_info.append((t.name, active_length))
                                else:
                                    kept_info.append((t.name, active_length))
                            except Exception:
                                pass
                    # Falls min_frames == 0 einfach alle als "kept" zählen (aber dennoch nur aktive Frames loggen)
                    else:
                        for t in tracking.tracks:
                            try:
                                active_frames = set()
                                for m in t.markers:
                                    if not hasattr(m, "frame"):
                                        continue
                                    if _is_marker_disabled(t, m):
                                        continue
                                    active_frames.add(m.frame)
                                kept_info.append((t.name, len(active_frames)))
                            except Exception:
                                pass

                    if flagged_names:
                        delete_tracks_by_names(bpy.context, flagged_names)

                    try:
                        print(f"[TRACK_LENGTH_VALIDATION] min_frames={min_frames} "
                              f"deleted={len(deleted_info)} kept={len(kept_info)} "
                              f"(active frames only)")
                        if deleted_info:
                            print("  Deleted Tracks:", ", ".join(f"{n}:{l}" for n, l in deleted_info))
                        else:
                            print("  Deleted Tracks: None")
                        if kept_info:
                            print("  Kept Tracks:", ", ".join(f"{n}:{l}" for n, l in kept_info))
                        else:
                            print("  Kept Tracks: None")
                    except Exception:
                        pass

                self._rebuild_good_tracks(context, reason="Post-Stage2 cleanup")

                frame = find_first_weak_frame_solve(context)
                if frame is None:
                    # ----------------- Solve-Guard -----------------
                    if not has_solve_basis(context):
                        # Solve-Basis fehlt → Suche Weak-Frame mit *2 Marker-Schwelle
                        from ...Helper.low_marker_frame import find_first_weak_frame
                        new_frame = find_first_weak_frame(context)

                        if new_frame is None:
                            # auch mit erhöhtem Target nichts gefunden → dennoch abbrechen
                            valid, spans = get_solve_basis_stats(context)
                            self.report({'ERROR'},
                                        f"Keine solve-fähige Basis vorhanden "
                                        f"(gültige={valid}, Spannen={spans}).")
                            return {'CANCELLED'}

                        # Playhead setzen und Low-Marker-Cycle erneut starten
                        self.report({'INFO'},
                                    "Solve-Basis zu schwach → fokussierter Weak-Frame-Retry (×2 Marker-Ziel).")
                        bpy.context.scene.frame_current = new_frame

                        bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                        return {'FINISHED'}
                    # Solve möglich → jetzt Resolve starten
                    bpy.ops.kaiserlich_tracker.master_resolve_operator('INVOKE_DEFAULT')
                    return {'FINISHED'}

                # Tracking-Defaults optional aktualisieren (nicht löschen!)
                update_default_sizes(context)

                # Cache-Keys bereinigen, aber nichts mehr überschreiben
                for k in ("frame_value_cache", "kaiserlich_best_thresholds"):
                    if k in scene:
                        del scene[k]

            except Exception as ex:
                self.report({'ERROR'}, f"Error during filter process: {ex}")
                return {'CANCELLED'}

        # ------------------------------------------------------------------
        # Frame setzen + Folgeoperator starten
        # ------------------------------------------------------------------
        scene.frame_current = frame

        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception as e:
            pass

        bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')

        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_cycle_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_cycle_operator)
