"""Utility: remove tracks with high reprojection error."""

import bpy


def cleanup_marker_errors(limit):
    """Remove tracks with high reprojection error when too many markers exist."""

    clip = bpy.context.space_data.clip
    if not clip:
        print("\u2757 Kein MovieClip im aktuellen Kontext verf\u00fcgbar.")
        return

    obj = clip.tracking.objects.active
    if obj is None or not obj.is_camera:
        print("\u2757 Kein aktives Kamera-Tracking-Objekt vorhanden.")
        return

    try:
        bpy.ops.clip.solve_camera()
        print("[Cleanup] camera solve finished")
    except Exception as e:
        print(f"[Cleanup] solve failed: {e}")
        return

    if not clip.tracking.reconstruction.is_valid:
        print("\u2757 Camera solve wurde ausgef\u00fchrt, aber keine g\u00fcltige L\u00f6sung erzeugt.")
        return

    marker_data = clip.tracking.tracks
    if not marker_data:
        return

    start_frame = int(clip.frame_start)
    end_frame = int(clip.frame_start + clip.frame_duration - 1)

    changes_made = True
    while changes_made:
        changes_made = False

        for frame in range(start_frame, end_frame + 1):
            active_markers = []
            for track in marker_data:
                marker = track.markers.find_frame(frame)
                if marker and not marker.mute:
                    error = getattr(marker, "error", 0.0)
                    active_markers.append((track, error))

            if len(active_markers) > limit:
                bpy.context.scene.frame_current = frame
                print(
                    f"Found frame {frame} with {len(active_markers)} active markers (more than {limit})."
                )
                active_markers.sort(key=lambda x: x[1], reverse=True)
                while len(active_markers) > limit:
                    worst_track, error = active_markers.pop(0)
                    if error < 2.0:
                        print(
                            f"Skipped deletion of marker with error {error:.4f} (below threshold)"
                        )
                        continue
                    clip.tracking.tracks.remove(worst_track)
                    print(
                        f"Deleted entire track '{worst_track.name}' due to error {error:.4f} at frame {frame}"
                    )
                    changes_made = True

                break

    final_tracks = len(clip.tracking.tracks)
    print(f"Final track count: {final_tracks}")
    print("All frames now within marker limit.")

