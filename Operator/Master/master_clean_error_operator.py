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
            print("[CLEAN ERROR] ❌ Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        tracks = getattr(clip.tracking, "tracks", None)
        if not tracks:
            print("[CLEAN ERROR] ❌ Keine Tracks gefunden.")
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

        print(f"[CLEAN ERROR] Durchschnittsfehler: {avg_error}, Max Error Value: {max_error_value}")

        # ------------------------------------------------------------
        # Early termination if thresholds are missing
        # ------------------------------------------------------------
        if avg_error is None or max_error_value is None:
            print("[CLEAN ERROR] ⚠️ Kein gültiger Schwellenwert, breche ab.")
            return {'FINISHED'}

        # ------------------------------------------------------------
        # Delete tracks exceeding threshold
        # ------------------------------------------------------------
        if avg_error > max_error_value:
            limit = avg_error * 2.0
            try:
                from ...Helper.delete import delete_track_by_name
            except Exception:
                print("[CLEAN ERROR] ❌ Helper delete_track_by_name nicht gefunden.")
                return {'CANCELLED'}

            deleted = 0
            for r in results:
                if r["error"] is not None and r["error"] > limit:
                    try:
                        delete_track_by_name(context, r["name"])
                        deleted += 1
                    except Exception:
                        pass
            print(f"[CLEAN ERROR] {deleted} Tracks gelöscht, da über Limit ({limit:.3f}).")

        # ------------------------------------------------------------
        # Store all track IDs globally (ID-basiert, wie good_tracks)
        # ------------------------------------------------------------
        try:
            if "good_tracks" in scene:
                del scene["good_tracks"]
            if "best_tracks" in scene:
                del scene["best_tracks"]
            if "best_track_ids" in scene:
                del scene["best_track_ids"]

            all_tracks = list(clip.tracking.tracks)
            id_list = [str(id(t)) for t in all_tracks]

            scene["best_track_ids"] = id_list
            scene["best_tracks"] = id_list  # Alias für Kompatibilität

            print(f"[CLEAN ERROR] 🔹 {len(id_list)} best_track_ids gespeichert.")
            if id_list:
                print(f"[CLEAN ERROR] Beispiel-IDs: {id_list[:10]}{' ...' if len(id_list) > 10 else ''}")

        except Exception as e:
            print(f"[CLEAN ERROR] ⚠️ Fehler beim Speichern der best_tracks: {e}")

        # ------------------------------------------------------------
        # Trigger next operator
        # ------------------------------------------------------------
        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            print("[CLEAN ERROR] Master Cycle Operator gestartet.")
        except Exception as e:
            print(f"[CLEAN ERROR] ⚠️ Fehler beim Starten des Master Cycle Operators: {e}")

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