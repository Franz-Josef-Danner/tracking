import bpy
import time


def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None


def track_has_internal_gaps(track):
    frames = sorted([m.frame for m in track.markers])
    if len(frames) < 3:
        return False
    return any(frames[i] - frames[i - 1] > 1 for i in range(1, len(frames)))


def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    total_deleted = 0
    frame_start, frame_end = frame_range

    for fi in range(frame_start + 1, frame_end - 1):
        f1, f2 = fi - 1, fi + 1
        marker_data = []

        for track in tracks:
            p1 = get_marker_position(track, f1)
            p2 = get_marker_position(track, fi)
            p3 = get_marker_position(track, f2)

            if not (p1 and p2 and p3):
                continue

            x, y = p2[0] * width, p2[1] * height
            if not (xmin <= x < xmax and ymin <= y < ymax):
                continue

            vxm = (p2[0] - p1[0]) + (p3[0] - p2[0])
            vym = (p2[1] - p1[1]) + (p3[1] - p2[1])
            marker_data.append((track, vxm, vym))


        if not marker_data:
            continue

        vxa = sum(vx for _, vx, _ in marker_data) / len(marker_data)
        vya = sum(vy for _, _, vy in marker_data) / len(marker_data)
        va = (vxa + vya) / 2

        eb = max([abs((vx + vy) / 2 - va) for _, vx, vy in marker_data], default=0.0001)
        eb = max(eb, 0.0001)

        while eb > ee:
            eb *= 0.95
            for track, vx, vy in marker_data:
                vm = (vx + vy) / 2
                if abs(vm - va) >= eb:
                    for f in (f1, fi, f2):
                        if track.markers.find_frame(f):
                            track.markers.delete_frame(f)
                            total_deleted += 1

    return total_deleted


def clean_error_tracks(context, space):
    scene = context.scene
    clip = space.clip
    tracks = clip.tracking.tracks

    for track in tracks:
        track.select = False

    width, height = clip.size
    frame_range = (scene.frame_start, scene.frame_end)

    ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
    fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
    teilfaktoren = [1, 2, 4]

    total_deleted_all = 0
    for ee, division in zip(fehlergrenzen, teilfaktoren):
        for xIndex in range(division):
            for yIndex in range(division):
                xmin = xIndex * (width / division)
                xmax = (xIndex + 1) * (width / division)
                ymin = yIndex * (height / division)
                ymax = (yIndex + 1) * (height / division)
                total_deleted_all += run_cleanup_in_region(
                    tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height
                )
    return total_deleted_all, 0.0

def delete_marker_path(track, from_frame, direction):
    to_delete = []
    for m in track.markers:
        if (direction == 'forward' and m.frame >= from_frame) or \
           (direction == 'backward' and m.frame <= from_frame):
            to_delete.append(m.frame)

    for f in to_delete:
        track.markers.delete_frame(f)

def get_track_segments(track):
    frames = sorted([m.frame for m in track.markers])
    if not frames:
        return []

    segments = []
    current_segment = [frames[0]]
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] == 1:
            current_segment.append(frames[i])
        else:
            segments.append(current_segment)
            current_segment = [frames[i]]
    segments.append(current_segment)
    return segments

# 🆕 Neue Hilfsfunktion hier einfügen:
def is_marker_valid(track, frame):
    try:
        marker = track.markers.find_frame(frame)
        return marker is not None and hasattr(marker, "co")
    except Exception as e:
        return False

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    with context.temp_override(area=area, region=region, space_data=space):

        for track in original_tracks:
            segments = get_track_segments(track)
            frames = [m.frame for m in track.markers]
            for seg in segments:
                delete_marker_path(track, seg[-1] + 1, 'forward')
                
        for track in new_tracks:
            # 💡 WICHTIG: Force-Update durch Frame-Jump + Redraw je Track
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            bpy.context.view_layer.update()
            time.sleep(0.05)

            segments = get_track_segments(track)
            frames = [m.frame for m in track.markers]
            for seg in segments:
                delete_marker_path(track, seg[0] - 1, 'backward')

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip_editor_area = clip_editor_region = clip_editor_space = None

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        clip_editor_area = area
                        clip_editor_region = region
                        clip_editor_space = area.spaces.active

        if not clip_editor_space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        clean_error_tracks(context, clip_editor_space)
        clip = clip_editor_space.clip
        tracks = clip.tracking.tracks

        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            self.report({'INFO'}, "Keine Tracks mit Lücken gefunden.")
            return {'FINISHED'}

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=clip_editor_space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=5)
            scene.frame_set(scene.frame_current)
            bpy.context.view_layer.update()
            time.sleep(0.2)



        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        clear_path_on_split_tracks_segmented(
            context, clip_editor_area, clip_editor_region, clip_editor_space, original_tracks, new_tracks
        )

        self.report({'INFO'}, f"{len(new_tracks)} duplizierte Tracks erkannt und bereinigt.")
        return {'FINISHED'}
