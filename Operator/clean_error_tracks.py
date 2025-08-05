import bpy

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

def clean_error_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

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
            for frame in range(frame_range[0] + 1, frame_range[1] - 1):
                p1 = get_marker_position(track, frame - 1)
                p2 = get_marker_position(track, frame)
                p3 = get_marker_position(track, frame + 1)

                if not (p1 and p2 and p3):
                    continue

                vxm = (p3[0] - p1[0]) / 2
                vym = (p3[1] - p1[1]) / 2
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

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks"
    bl_description = "Löscht fehlerhafte Tracks anhand eines adaptiven Fehlerschwellwerts"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def execute(self, context):
        deleted, max_error = clean_error_tracks(context)
        if deleted:
            self.report({'INFO'}, f"Insgesamt {deleted} Marker gelöscht. Max. Fehler: {max_error:.6f}")
        else:
            self.report({'INFO'}, "Keine Marker gelöscht.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_clean_error_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_clean_error_tracks)
