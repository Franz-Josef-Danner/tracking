# Operator/Master/master_clean_error_operator.py
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty


def _find_active_clip(context: bpy.types.Context):
    """Sucht zuerst Clip im Clip-Editor, fallback auf active strip (Sequencer)."""
    clip = None
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
    """Ermittelt Solve/Error-Werte; löscht Tracks oberhalb Schwelle (silent)."""
    bl_idname = "kaiserlich_tracker.clean_error_operator"
    bl_label = "Kaiserlich: Clean Error (silent)"
    bl_options = {'REGISTER', 'INTERNAL'}

    sort_desc: BoolProperty(
        name="Sort descending",
        description="Sortiere absteigend nach Error (höchste zuerst)",
        default=True
    )

    def _get_track_error(self, track) -> float | None:
        """Ermittelt Solve Error oder mittleren Markerfehler."""
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

        if avg_error is None or max_error_value is None:
            return {'FINISHED'}

        if avg_error > max_error_value:
            limit = avg_error * 2.0
            try:
                from ...Helper.delete import delete_track_by_name
            except Exception:
                return {'CANCELLED'}

            for r in results:
                if r["error"] is not None and r["error"] > limit:
                    try:
                        delete_track_by_name(context, r["name"])
                    except Exception:
                        pass

        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
        except Exception:
            pass

        return {'FINISHED'}


classes = (KAISERLICHTRACKER_OT_clean_error_operator,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
