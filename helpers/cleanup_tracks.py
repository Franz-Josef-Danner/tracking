import bpy
from ..helpers.delete_tracks import delete_selected_tracks


def max_track_error(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> float:
    """Return the maximum absolute error among tracking markers."""
    width, height = clip.size
    start = scene.frame_start + 1
    end = scene.frame_end

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
                    "xv1": xv1,
                    "xv2": xv2,
                    "yv1": yv1,
                    "yv2": yv2,
                    "track": track,
                })
        collect(valid)
        groups = {}
        cell_w = width / 2
        cell_h = height / 2
        for info in valid:
            col = int(info["mx_mean"] // cell_w)
            row = int(info["my_mean"] // cell_h)
            groups.setdefault((col, row), []).append(info)
        for subset in groups.values():
            collect(subset)
        groups = {}
        cell_w = width / 4
        cell_h = height / 2
        for info in valid:
            col = int(info["mx_mean"] // cell_w)
            row = int(info["my_mean"] // cell_h)
            groups.setdefault((col, row), []).append(info)
        for subset in groups.values():
            collect(subset)
    return max_error


def cleanup_error_tracks(scene: bpy.types.Scene, clip: bpy.types.MovieClip) -> None:
    """Delete tracking markers while decreasing the error threshold."""
    original = scene.error_threshold
    max_err = max_track_error(scene, clip)
    scene.error_threshold = max_err
    threshold = max_err
    while threshold >= original:
        while cleanup_pass(scene, clip, threshold):
            pass
        threshold *= 0.9
        scene.error_threshold = threshold
    scene.error_threshold = original


def cleanup_pass(scene: bpy.types.Scene, clip: bpy.types.MovieClip, threshold: float) -> bool:
    """Run a single cleanup pass and return True if tracks were deleted."""
    if not bpy.ops.clip.track_cleanup.poll():
        return False
    bpy.ops.clip.track_cleanup()
    selected = sum(1 for t in clip.tracking.tracks if t.select)
    if selected:
        delete_selected_tracks()
        return True
    return False
