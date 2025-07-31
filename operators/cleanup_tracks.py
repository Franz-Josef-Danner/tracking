import bpy
from ..helpers.delete_tracks import delete_selected_tracks

def max_track_error(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> float:
    print("→ Berechne maximalen Trackingfehler")
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end - 1
    max_error = 0.0

    for frame in range(start, end):
        print(f"  Frame {frame}")
        velocities = []
        for track in clip.tracking.tracks:
            coords = []
            for f in (frame - 1, frame, frame + 1):
                marker = track.markers.find_frame(f, exact=True)
                if not marker:
                    print(f"    Marker nicht gefunden für Frame {f} in Track '{track.name}'")
                    break
                if marker.mute:
                    print(f"    Marker in Frame {f} ist stummgeschaltet (mute) in Track '{track.name}'")
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

    print(f"→ Maximaler Fehler berechnet: {max_error:.3f}")
    return max_error

def cleanup_pass(scene, clip, threshold: float) -> bool:
    print(f"→ Starte Cleanup-Pass bei Threshold {threshold:.3f}")
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end - 1
    selected = False
    tracks_checked = 0
    tracks_selected = 0

    for track in clip.tracking.tracks:
        tracks_checked += 1
        errors = []
        for f in range(start, end):
            coords = []
            for offset in (-1, 0, 1):
                marker = track.markers.find_frame(f + offset, exact=True)
                if not marker:
                    print(f"    ❌ Kein Marker in Frame {f + offset} für Track '{track.name}'")
                    break
                if marker.mute:
                    print(f"    🚫 Marker stummgeschaltet in Frame {f + offset} (Track '{track.name}')")
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
            print(f"  Track '{track.name}' hat max Fehler {max_err:.3f}")
            if max_err > threshold:
                print(f"    ✅ Track '{track.name}' überschreitet Threshold → markieren zur Löschung")
                track.select = True
                selected = True
                tracks_selected += 1
            else:
                print(f"    ⚪ Track '{track.name}' liegt unterhalb Threshold")
                track.select = False
        else:
            print(f"  ⚠️ Track '{track.name}' enthält keine gültigen Marker über alle Frames")

    print(f"→ Überprüfte Tracks: {tracks_checked}, selektierte Tracks: {tracks_selected}")

    if selected:
        print("→ Lösche selektierte Tracks...")
        delete_selected_tracks()
        print("→ Tracks wurden gelöscht.")
        return True

    print("→ Keine Tracks markiert – nichts gelöscht.")
    return False

def cleanup_error_tracks(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> bool:
    print("→ Starte vollständigen Cleanup-Vorgang...")
    original_threshold = scene.error_threshold
    max_error = max_track_error(scene, clip)
    print(f"→ Start bei max_error = {max_error:.3f}, untere Grenze = {original_threshold}")

    threshold = max_error
    deleted_any = False
    iteration = 0

    while threshold >= original_threshold:
        iteration += 1
        print(f"\n===== Iteration {iteration} - Threshold: {threshold:.3f} =====")
        deleted_this_round = False
        while cleanup_pass(scene, clip, threshold):
            deleted_any = True
            deleted_this_round = True
        if not deleted_this_round:
            print(f"→ Kein Track gelöscht bei Schwelle {threshold:.3f}")
        threshold *= 0.9
        scene.error_threshold = threshold

    print("\n→ Cleanup abgeschlossen.")
    print(f"→ Insgesamt Tracks gelöscht: {'JA' if deleted_any else 'NEIN'}")
    scene.error_threshold = original_threshold
    return deleted_any

class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    """Bereinigt fehlerhafte Marker basierend auf Bewegungsabweichung"""
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Cleanup Tracks"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip im Kontext.")
            return {'CANCELLED'}

        deleted = cleanup_error_tracks(context.scene, clip)
        if deleted:
            self.report({'INFO'}, "✅ Cleanup abgeschlossen. Fehlerhafte Marker wurden gelöscht.")
        else:
            self.report({'INFO'}, "ℹ️ Cleanup abgeschlossen. Keine Marker lagen über dem Fehler-Schwellenwert.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)
