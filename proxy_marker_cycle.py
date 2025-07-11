import bpy
from .marker_count_property import count_new_markers
from .combined_cycle import adjust_marker_count_plus, ensure_margin_distance


class CLIP_OT_proxy_marker_cycle(bpy.types.Operator):
    """Detect markers after proxy generation until enough are found."""

    bl_idname = "clip.proxy_marker_cycle"
    bl_label = "Proxy Marker Detect Cycle"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        threshold = 0.1

        while True:
            margin, distance, _ = ensure_margin_distance(clip, threshold)
            initial = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
                placement='FRAME',
            )
            new_tracks = [t for t in clip.tracking.tracks if t.name not in initial]
            for t in new_tracks:
                t.name = f"NEU_{t.name}"

            new_marker = count_new_markers(context)
            if new_marker >= context.scene.min_marker_count_plus:
                break

            adjust_marker_count_plus(context.scene, 10)
            base_plus = context.scene.min_marker_count_plus
            factor = (new_marker + 0.1) / base_plus
            threshold = max(threshold * factor, 0.0001)
            self._delete_new_tracks(context)

        # Cleanup and rename markers
        for track in clip.tracking.tracks:
            if track.name.startswith("NEU_"):
                track.name = f"TRACK_{track.name[4:]}"
        return {'FINISHED'}

    def _delete_new_tracks(self, context):
        clip = context.space_data.clip
        if not clip:
            return
        for t in clip.tracking.tracks:
            t.select = t.name.startswith("NEU_")
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                space = area.spaces.active
                if region and space:
                    with context.temp_override(area=area, region=region, space_data=space):
                        bpy.ops.clip.delete_track()
                    break


def register():
    bpy.utils.register_class(CLIP_OT_proxy_marker_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_proxy_marker_cycle)


if __name__ == "__main__":
    register()
