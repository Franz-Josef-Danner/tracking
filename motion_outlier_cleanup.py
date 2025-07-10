import bpy

# === Hauptfunktion: Marker bereinigen ===
def cleanup_tracking_markers(context, base_et):  # base_et = (et1, et2, et3)
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    total_deleted = 0

    divisions = [(1, base_et[0]), (2, base_et[1]), (4, base_et[2])]

    def marker_at(track, frame):
        try:
            return track.markers.find_frame(frame)
        except:
            return None

    def get_tg(marker1, marker2, marker3):
        t1x = marker2.co[0] - marker1.co[0]
        t2x = marker3.co[0] - marker2.co[0]
        tgx = t1x + t2x
        t1y = marker2.co[1] - marker1.co[1]
        t2y = marker3.co[1] - marker2.co[1]
        tgy = t1y + t2y
        return tgx, tgy

    def delete_tracks(tracks_to_delete, context):
        nonlocal total_deleted
        total_deleted += len(tracks_to_delete)
        for t in tracks:
            t.select = False
        for t in tracks_to_delete:
            t.select = True

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                with context.temp_override(
                                    area=area,
                                    region=region,
                                    space_data=space,
                                ):
                                    bpy.ops.clip.delete_track()
                                return

    def filter_marker_group(tracks_subset, et, frame_current):
        tgx_list, tgy_list = [], []
        valid_tracks = []

        for track in tracks_subset:
            m1 = marker_at(track, frame_current - 1)
            m2 = marker_at(track, frame_current)
            m3 = marker_at(track, frame_current + 1)
            if m1 and m2 and m3:
                tgx, tgy = get_tg(m1, m2, m3)
                tgx_list.append(tgx)
                tgy_list.append(tgy)
                valid_tracks.append((track, tgx, tgy))

        if not valid_tracks:
            return False

        tx = sum(tgx_list) / len(tgx_list)
        ty = sum(tgy_list) / len(tgy_list)

        to_delete = [
            track for track, tgx, tgy in valid_tracks
            if abs(tgx - tx) > et or abs(tgy - ty) > et
        ]

        if to_delete:
            delete_tracks(to_delete, context)

        return True

    def process_region(xmin, xmax, ymin, ymax, et, frame_current):
        region_tracks = []
        for track in tracks:
            marker = marker_at(track, frame_current)
            if marker:
                x, y = marker.co
                if xmin <= x <= xmax and ymin <= y <= ymax:
                    region_tracks.append(track)

        return filter_marker_group(region_tracks, et, frame_current)

    # Durch alle Frames laufen (außer erstem und letztem)
    start = context.scene.frame_start + 1
    end = context.scene.frame_end - 1
    for frame in range(start, end + 1):
        context.scene.frame_current = frame
        active_marker_found = False

        for div, et in divisions:
            step = 1.0 / div
            for i in range(div):
                for j in range(div):
                    xmin = i * step
                    xmax = (i + 1) * step
                    ymin = j * step
                    ymax = (j + 1) * step
                    found = process_region(xmin, xmax, ymin, ymax, et, frame)
                    active_marker_found = active_marker_found or found

        if not active_marker_found:
            print(f"Keine Marker mehr bei Frame {frame}. Prozess beendet.")
            break

    print(f"Tracking Marker Cleanup abgeschlossen. Insgesamt gelöscht: {total_deleted} Marker.")

# === UI Operator ===
class CLIP_OT_clean_tracking_markers(bpy.types.Operator):
    bl_idname = "clip.clean_tracking_markers"
    bl_label = "Wackelige Marker bereinigen"
    bl_description = "Bereinigt Marker mit inkonsistenter Bewegung über alle Frames"
    bl_options = {'REGISTER', 'UNDO'}

    ,
        description="Toleranzen für Ganzbild, Halbierung und Viertelung"
    )

    @classmethod
    def poll(cls, context):
        return context.space_data.clip is not None

    def execute(self, context):
        cleanup_tracking_markers(context, (0.04, 0.02, 0.01))
        return {'FINISHED'}

# === UI Panel ===
class CLIP_PT_tracking_cleanup_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking Cleanup'
    bl_label = "Tracking Cleanup"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        op = layout.operator("clip.clean_tracking_markers", icon="TRACKING_FORWARDS")
        
# === Registrierung ===
classes = (
    CLIP_OT_clean_tracking_markers,
    CLIP_PT_tracking_cleanup_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    

def unregister():
    
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
