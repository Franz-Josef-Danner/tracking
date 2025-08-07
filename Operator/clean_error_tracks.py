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

def mute_marker_path(track, from_frame, direction, mute=True):
    for m in track.markers:
        if (direction == 'forward' and m.frame >= from_frame) or \
           (direction == 'backward' and m.frame <= from_frame):
            m.mute = mute

def mute_outside_segment_markers(track):
    """
    Mutes all markers in the given track that are not part of a continuous segment.
    """
    # Segment-Frames als Set erfassen
    segments = get_track_segments(track)
    valid_frames = set()
    for segment in segments:
        valid_frames.update(segment)

    # Alle Marker prüfen
    for marker in track.markers:
        if marker.frame not in valid_frames:
            print(f"[Mute] Track '{track.name}': Marker @ Frame {marker.frame} außerhalb aller Segmente → mute")
            marker.mute = True

def mute_all_outside_segment_markers(tracks):
    for track in tracks:
        mute_outside_segment_markers(track)

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    with context.temp_override(area=area, region=region, space_data=space):
        
        # 🔴 ORIGINAL-TRACKS: Vorderes Segment behalten → alles danach muten
        for track in original_tracks:
            segments = get_track_segments(track)

            # Optional: alle Marker vorher ent-muten (wie ENABLE)
            for m in track.markers:
                m.mute = False

            for seg in segments:
                mute_marker_path(track, seg[-1] + 1, 'forward', mute=True)

        # 🔵 NEW-TRACKS: Hinteres Segment behalten → alles davor muten
        for track in new_tracks:
            # 💡 Force-Update (wie bisher)
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            bpy.context.view_layer.update()
            time.sleep(0.05)

            segments = get_track_segments(track)

            # Optional: alle Marker vorher ent-muten (wie ENABLE)
            for m in track.markers:
                m.mute = False

            for seg in segments:
                mute_marker_path(track, seg[0] - 1, 'backward', mute=True)

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
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            original_tracks, new_tracks
        )

        # 🧩 Jetzt rekursiv weiter, bis keine Gaps mehr bestehen
        recursive_split_cleanup(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            tracks
        )

        return {'FINISHED'}

def mute_unassigned_markers(tracks):
    """
    Mute alle Marker, die entweder:
    - außerhalb von Segmenten mit Länge ≥ 2 liegen
    - oder am Beginn/Ende eines Tracks als einzelner Marker stehen
    """
    for track in tracks:
        segments = get_track_segments(track)
        valid_frames = set()
        
        for segment in segments:
            if len(segment) >= 2:
                valid_frames.update(segment)

        all_frames = set(m.frame for m in track.markers)

        for marker in track.markers:
            f = marker.frame
            # Mute, wenn nicht Teil eines ≥2-Segments oder am Track-Beginn/-Ende mit nur 1 Marker
            if f not in valid_frames:
                marker.mute = True
                print(f"[Mute] Einzelner Marker in Track '{track.name}' bei Frame {f} → mute")

def recursive_split_cleanup(context, area, region, space, tracks):
    scene = context.scene
    iteration = 0
    previous_gap_count = -1
    MAX_ITERATIONS = 10

    # Initialisieren (falls nicht vorhanden)
    if "processed_tracks" not in scene:
        scene["processed_tracks"] = []

    while iteration < MAX_ITERATIONS:
        iteration += 1

        # Hole verarbeitete Track-Namen als reguläre Python-Liste
        processed = list(scene.get("processed_tracks", []))

        # Finde nur Tracks mit Gaps, die noch nicht verarbeitet wurden
        original_tracks = [
            t for t in tracks
            if track_has_internal_gaps(t) and t.name not in processed
        ]
        print(f"🔁 Iteration {iteration}: {len(original_tracks)} unverarbeitete Tracks mit Gaps")

        if not original_tracks:
            print("✅ Keine weiteren verarbeitbaren Gaps gefunden – fertig.")
            break

        if previous_gap_count == len(original_tracks):
            print("🛑 Kein Fortschritt – breche Rekursion ab.")
            break

        previous_gap_count = len(original_tracks)

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=5)
            scene.frame_set(scene.frame_current)
            bpy.context.view_layer.update()
            time.sleep(0.2)

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        # Tracks (original und neu) als verarbeitet markieren
        for t in original_tracks + new_tracks:
            if t.name not in processed:
                processed.append(t.name)

        # Rückspeichern
        scene["processed_tracks"] = processed

        clear_path_on_split_tracks_segmented(
            context, area, region, space,
            original_tracks, new_tracks
        )

    # 🔚 Letzter Schritt: kurze Tracks bereinigen – im gültigen UI-Kontext
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.clean_short_tracks('INVOKE_DEFAULT')

    # 🧩 Danach: Vereinzelte Marker, die außerhalb von Segmenten liegen, muten
    mute_unassigned_markers(tracks)

    return {'FINISHED'}
