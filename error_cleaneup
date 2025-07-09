import bpy

# Parameter: Schwellenwert für Markeranzahl
MARKER_LIMIT = 10  # <- Hier den gewünschten Wert für "x" eintragen

def find_frame_with_few_markers(limit):
    # Versuche Solve durchzuführen, um Marker-Fehler zu generieren
    try:
        bpy.ops.clip.solve_camera()
        print("✔ Camera solve completed to access marker error data.")
    except Exception as e:
        print(f"❗ Solve failed: {e}")
        return
    clip = bpy.context.space_data.clip
    if not clip:
        return

    marker_data = clip.tracking.tracks
    if not marker_data:
        return

    total_tracks = len(marker_data)
    max_error = 0.0
    for track in marker_data:
        for marker in track.markers:
            if hasattr(marker, 'error') and marker.error > max_error:
                max_error = marker.error

    print(f"Initial track count: {total_tracks}")
    print(f"Maximum marker error in scene: {max_error:.4f}")
    clip = bpy.context.space_data.clip
    if not clip:
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
                    active_markers.append((track, track.markers.find_frame(frame).error if hasattr(track.markers.find_frame(frame), 'error') else 0.0))

            if len(active_markers) > limit:
                bpy.context.scene.frame_current = frame
                print(f"Found frame {frame} with {len(active_markers)} active markers (more than {limit}).")

                # Sortiere Marker nach Fehlerwert absteigend (höchster Fehler = schlechtester Marker)
                active_markers.sort(key=lambda x: x[1], reverse=True)

                # Lösche Marker bis Limit erreicht ist
                while len(active_markers) > limit:
                    worst_track, error = active_markers.pop(0)
                    if error < 2.0:
                        print(f"Skipped deletion of marker with error {error:.4f} (below threshold)")
                        continue
                    clip.tracking.tracks.remove(worst_track)
                    print(f"Deleted entire track '{worst_track.name}' due to error {error:.4f} at frame {frame}")
                    changes_made = True

                break  # Neu starten

    final_tracks = len(clip.tracking.tracks)
    print(f"Final track count: {final_tracks}")
    print("All frames now within marker limit.")

# Panel + Button definieren
class CLIP_PT_FindSparseMarkerFrame(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Marker Tools'
    bl_label = 'Find Sparse Marker Frame'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.find_sparse_marker_frame", text="Jump to Dense Frame")

class CLIP_OT_FindSparseMarkerFrameOperator(bpy.types.Operator):
    bl_idname = "clip.find_sparse_marker_frame"
    bl_label = "Find Frame with Many Markers"

    def execute(self, context):
        find_frame_with_few_markers(MARKER_LIMIT)
        return {'FINISHED'}

# Registrierung
classes = [CLIP_PT_FindSparseMarkerFrame, CLIP_OT_FindSparseMarkerFrameOperator]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
