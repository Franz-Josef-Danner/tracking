import bpy
from ..helpers.delete_tracks import delete_selected_tracks

def max_track_error(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> float:
    """Return the maximum absolute error among tracking markers."""
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end - 1

    max_error = 0.0

    def collect(tracks_info):
        nonlocal max_error
        if not tracks_info:
            return
        xvg = sum(t["xv"] for t in tracks_info) / len(tracks_info)
        yvg = sum(t["yv"] for t in tracks_info) / len(tracks_info)
        for info in tracks_info:
            etx = xvg - info["xv"]
            ety = yvg - info["yv"]
            error_val = max(abs(etx), abs(ety))
            if error_val > max_error:
                max_error = error_val

    for frame in range(start, end):
        valid = []
        for track in clip.tracking.tracks:
            coords = []
            for f in (frame - 1, frame, frame + 1):
                marker = track.markers.find_frame(f, exact=True)
                if marker is None or marker.mute:
                    break
                coords.append((marker.co[0] * width, marker.co[1] * height))
            if len(coords) == 3:
                px1, py1 = coords[0]
                px2, py2 = coords[1]
                px3, py3 = coords[2]
                xv1 = px1 - px2
                xv2 = px2 - px3
                yv1 = py1 - py2
                yv2 = py2 - py3
                xv = xv1 + xv2
                yv = yv1 + yv2
                mx_mean = (px1 + px2 + px3) / 3.0
                my_mean = (py1 + py2 + py3) / 3.0
                valid.append({
                    "mx_mean": mx_mean,
                    "my_mean": my_mean,
                    "xv": xv,
                    "yv": yv,
                    "track": track,
                })
        collect(valid)
    return max_error


def cleanup_error_tracks(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> bool:
    """Delete tracking markers while decreasing the error threshold."""
    original = scene.error_threshold
    max_err = max_track_error(scene, clip)
    print(f"Maximaler Trackingfehler: {max_err:.3f}")
    scene.error_threshold = max_err
    threshold = max_err

    deleted_any = False
    while threshold >= original:
        print(f"Prüfe mit Threshold: {threshold:.3f}")
        changed = False
        while cleanup_pass(scene, clip, threshold):
            changed = True
            deleted_any = True
        threshold *= 0.9
        scene.error_threshold = threshold

        if not changed:
            break

    scene.error_threshold = original
    return deleted_any


def cleanup_pass(scene, clip, threshold: float) -> bool:
    width, height = clip.size
    selected = False

    for track in clip.tracking.tracks:
        errors = []

        for f in range(scene.frame_start + 1, scene.frame_end - 1):
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

                xv1 = px1 - px2
                xv2 = px2 - px3
                yv1 = py1 - py2
                yv2 = py2 - py3

                xv = xv1 + xv2
                yv = yv1 + yv2

                error = max(abs(xv), abs(yv))
                errors.append(error)

        if errors and max(errors) > threshold:
            print(f"Selektiert: {track.name} mit Fehler={max(errors):.2f}")
            track.select = True
            selected = True
        else:
            track.select = False

    if selected:
        delete_selected_tracks()
        return True

    return False
