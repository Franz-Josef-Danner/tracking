import bpy

def max_track_error(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> float:
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end - 1
    max_error = 0.0

    for frame in range(start, end):
        velocities = []
        for track in clip.tracking.tracks:
            coords = []
            for f in (frame - 1, frame, frame + 1):
                marker = track.markers.find_frame(f, exact=True)
                if not marker or marker.mute:
                    break
                coords.append((marker.co[0] * width, marker.co[1] * height))
            if len(coords) == 3:
                px1, py1 = coords[0]
                px2, py2 = coords[1]
                px3, py3 = coords[2]
                xv = (px1 - px2) + (px2 - px3)
                yv = (py1 - py2) + (py2 - py3)
                velocities.append((xv, yv))

        if velocities:
            avg_xv = sum(v[0] for v in velocities) / len(velocities)
            avg_yv = sum(v[1] for v in velocities) / len(velocities)
            for xv, yv in velocities:
                dx = abs(xv - avg_xv)
                dy = abs(yv - avg_yv)
                max_error = max(max_error, dx, dy)

    return max_error

def cleanup_pass(scene, clip, threshold: float) -> bool:
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end - 1
    selected = False

    for track in clip.tracking.tracks:
        errors = []
        for f in range(start, end):
            coords = []
            for offset in (-1, 0, 1):
                marker = track.markers.find_frame(f + offset, exact=True)
                if not marker or marker.mute:
                    break
                coords.append((marker.co[0] * width, marker.co[1] * height))
            if len(coords) == 3:
                px1, py1 = coords[0]
                px2, py2 = coords[1]
                px3, py3 = coords[2]
                xv = (px1 - px2) + (px2 - px3)
                yv = (py1 - py2) + (py2 - py3)
                error = max(abs(xv), abs(yv))
                errors.append(error)

        if errors:
            max_err = max(errors)
            if max_err > threshold:
                track.select = True
                selected = True
            else:
                track.select = False
        else:
            track.select = False

    return selected  # Kein Löschen mehr, nur Selektion

def cleanup_error_tracks(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> bool:
    final_threshold = 10.0
    max_error = max_track_error(scene, clip)
    threshold = max_error
    any_selected = False

    while threshold >= final_threshold:
        selected_this_round = cleanup_pass(scene, clip, threshold)
        if not selected_this_round:
            break
        any_selected = True
        threshold *= 0.9

    return any_selected

class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    """Selektiert Marker mit überdurchschnittlicher Bewegung"""
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Select Error Tracks"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip im Kontext.")
            return {'CANCELLED'}

        found = cleanup_error_tracks(context.scene, clip)
        if found:
            self.report({'INFO'}, "✅ Marker mit zu hoher Abweichung selektiert.")
        else:
            self.report({'INFO'}, "ℹ️ Keine Marker mit übermäßigem Bewegungsfehler gefunden.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)
