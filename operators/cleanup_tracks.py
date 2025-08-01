import bpy

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

def cleanup_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    # Alle Marker deselektieren
    for track in tracks:
        track.select = False

    ee_initial = (context.scene.error_per_track + 0.1) / 100
    threshold_factor = 0.9
    frame_range = (scene.frame_start, scene.frame_end)

    total_deleted_all = 0
    overall_max_error = 0.0

    for iteration in range(5):
        total_deleted = 0
        max_error = 0.0
        threshold = ee_initial * (threshold_factor ** iteration)

        for track in tracks:
            errors = []
            for frame in range(frame_range[0] + 2, frame_range[1] - 2):
                p0 = get_marker_position(track, frame - 2)
                p1 = get_marker_position(track, frame - 1)
                p2 = get_marker_position(track, frame)
                p3 = get_marker_position(track, frame + 1)
                p4 = get_marker_position(track, frame + 2)

                if not (p0 and p1 and p2 and p3 and p4):
                    continue

                vxm = ((p1[0] - p0[0]) + (p2[0] - p1[0]) + (p3[0] - p2[0]) + (p4[0] - p3[0])) / 4
                vym = ((p1[1] - p0[1]) + (p2[1] - p1[1]) + (p3[1] - p2[1]) + (p4[1] - p3[1])) / 4
                vm = (vxm + vym) / 2

                px = p2[0]
                py = p2[1]

                error = abs(px - (p1[0] + vm / 2)) + abs(py - (p1[1] + vm / 2))
                errors.append(error)

            if not errors:
                continue

            mean_error = sum(errors) / len(errors)
            max_error = max(max_error, mean_error)

            if mean_error > threshold:
                track.select = True
                total_deleted += 1

        if total_deleted == 0:
            break

        bpy.ops.clip.delete_track()
        total_deleted_all += total_deleted
        overall_max_error = max(overall_max_error, max_error)

    return total_deleted_all, overall_max_error


class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Cleanup Tracks"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def execute(self, context):
        deleted, max_error = cleanup_tracks(context)
        if deleted:
            self.report({'INFO'}, f"Insgesamt {deleted} Marker gelöscht. Max. Fehler: {max_error:.6f}")
        else:
            self.report({'INFO'}, "Keine Marker gelöscht.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)
