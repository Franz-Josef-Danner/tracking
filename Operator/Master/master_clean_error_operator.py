# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty



def _find_active_clip(context: bpy.types.Context):
    """First try to find a clip in the Clip Editor, fallback to the active strip (Sequencer)."""
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'CLIP_EDITOR':
                space = area.spaces.active
                if space and getattr(space, "clip", None):
                    return space.clip

    scene = context.scene
    if hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and getattr(strip, "clip", None):
            return strip.clip
    return None


class KAISERLICHTRACKER_OT_clean_error_operator(Operator):
    """Scan tracks, compute average error, and delete outliers if average exceeds threshold."""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Kaiserlich: Clean Error (silent)"
    bl_description = "Scan tracks, compute average error, and delete outliers if the average exceeds the scene threshold."
    bl_options = {'REGISTER', 'INTERNAL'}

    sort_desc: BoolProperty(
        name="Sort descending",
        description="Sort by error in descending order (highest first)",
        default=True
    )

    # ------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------
    def _get_track_error(self, track) -> float | None:
        """Retrieve solve error or mean per-marker reprojection error."""
        for name in ("average_error", "error", "solve_error", "reprojection_error"):
            val = getattr(track, name, None)
            if val is not None:
                try:
                    return float(val)
                except Exception:
                    pass
        try:
            vals = [float(m.error) for m in track.markers if hasattr(m, "error")]
            return sum(vals) / len(vals) if vals else None
        except Exception:
            return None

    # ------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------
    def execute(self, context):
        scene = context.scene
        clip = _find_active_clip(context)
        if clip is None:
            return {'CANCELLED'}

        tracks = getattr(clip.tracking, "tracks", None)
        if not tracks:
            return {'CANCELLED'}

        results = []
        for t in tracks:
            err = self._get_track_error(t)
            results.append({
                "name": t.name,
                "error": err,
                "track": t,
                "length": len(t.markers)
            })

        results.sort(
            key=lambda r: (r["error"] is None, -r["error"] if r["error"] else 0.0)
            if self.sort_desc else
            (r["error"] is None, r["error"] if r["error"] else 0.0)
        )

        valid = [r["error"] for r in results if r["error"] is not None]
        avg_error = sum(valid) / len(valid) if valid else None
        max_error_value = getattr(scene, "max_error_value", None)


        # ------------------------------------------------------------
        # Early termination if thresholds are missing
        # ------------------------------------------------------------
        if avg_error is None or max_error_value is None:
            return {'FINISHED'}

        # ------------------------------------------------------------
        # Delete tracks exceeding threshold
        # ------------------------------------------------------------
        if avg_error > max_error_value:
            limit = avg_error * 2.0
            try:
                from ...Helper.delete import delete_track_by_name
            except Exception:
                return {'CANCELLED'}
            ...
            # (delete loop ends here)
        # ------------------------------------------------------------
        # Remove GOOD_TRACKS (Clean Error darf diese ersetzen)
        # ------------------------------------------------------------
        print("[Kaiserlich][GOOD_TRACKS] Löschung gestartet...")

        for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map"):
            if k in scene:
                try:
                    print(f"[Kaiserlich][GOOD_TRACKS] Entferne Key: {k} | Wert: {scene.get(k)}")
                except Exception:
                    print(f"[Kaiserlich][GOOD_TRACKS] Entferne Key: {k} | Wert nicht lesbar")
                del scene[k]

        print("[Kaiserlich][GOOD_TRACKS] Säuberung abgeschlossen.")


        # ------------------------------------------------------------
        # Store BEST TRACKS (ID-basiert + Namen + UUID-Map)
        # ------------------------------------------------------------
        print("[Kaiserlich][BEST_TRACKS] Erstellung gestartet...")
        print(f"[Kaiserlich][BEST_TRACKS] Anzahl aktuell vorhandener Tracks: {len(list(clip.tracking.tracks))}")

        try:
            import uuid
            # Cleanup alte Keys
            for k in (
                "best_tracks", "best_tracks_names", "best_tracks_uuid_map",
                "best_track_ids"
            ):
                if k in scene:
                    del scene[k]

            all_tracks = list(clip.tracking.tracks)

            uuid_list, name_list, uuid_map = [], [], {}

            for t in all_tracks:
                uid = str(uuid.uuid4())
                uuid_list.append(uid)
                name_list.append(t.name)
                uuid_map[uid] = t.name

            print(f"[Kaiserlich][BEST_TRACKS] UUIDs gespeichert: {uuid_list}")
            print(f"[Kaiserlich][BEST_TRACKS] Namen gespeichert: {name_list}")
            print(f"[Kaiserlich][BEST_TRACKS] UUID-Map: {uuid_map}")

            # Speichern wie bei good_tracks
            scene["best_tracks"] = uuid_list
            scene["best_tracks_names"] = name_list
            scene["best_tracks_uuid_map"] = str(uuid_map)

            # Alias für ID-Kompatibilität (falls extern genutzt)
            scene["best_track_ids"] = [str(id(t)) for t in all_tracks]

            print("[Kaiserlich][BEST_TRACKS] Speicherung abgeschlossen.")

            # Konsistenzcheck
            if len(scene.get("best_tracks", [])) != len(scene.get("best_tracks_names", [])):
                print("[Kaiserlich][BEST_TRACKS][WARNUNG] UUID-Liste und Namensliste haben unterschiedliche Länge!")

        except Exception as e:
            print(f"[Kaiserlich][BEST_TRACKS] Speicherung fehlgeschlagen: {e}")

        # ------------------------------------------------------------
        # Trigger next operator
        # ------------------------------------------------------------
        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
        except Exception as e:
            pass

        return {'FINISHED'}


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------
classes = (KAISERLICHTRACKER_OT_clean_error_operator,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
