import bpy


def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

def track_has_internal_gaps(track):
    frames = sorted([marker.frame for marker in track.markers])
    if len(frames) < 3:
        return False  # Nicht genug Marker für sinnvolle Lückenanalyse

    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return True  # Markerabstand >1 → Lücke erkannt
    return False

def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    total_deleted = 0
    frame_start, frame_end = frame_range

    for fi in range(frame_start + 1, frame_end - 1):
        f1 = fi - 1
        f2 = fi + 1
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

        maa = len(marker_data)
        if maa == 0:
            continue

        vxa = sum(vx for _, vx, _ in marker_data) / maa
        vya = sum(vy for _, _, vy in marker_data) / maa
        va = (vxa + vya) / 2
        vm_diffs = [abs((vx + vy) / 2 - va) for _, vx, vy in marker_data]
        eb = max(vm_diffs) if vm_diffs else 0.0
        if eb < 0.0001:
            eb = 0.0001

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


def track_has_gaps(track, frame_start, frame_end):
    for f in range(frame_start, frame_end + 1):
        if not track.markers.find_frame(f):
            return True
    return False


def clean_error_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    for track in tracks:
        track.select = False

    width = clip.size[0]
    height = clip.size[1]
    frame_range = (scene.frame_start, scene.frame_end)

    ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
    fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
    teilfaktoren = [1, 2, 4]
    total_deleted_all = 0

    for stufe in range(len(fehlergrenzen)):
        ee = fehlergrenzen[stufe]
        division = teilfaktoren[stufe]

        for xIndex in range(division):
            for yIndex in range(division):
                xmin = xIndex * (width / division)
                xmax = (xIndex + 1) * (width / division)
                ymin = yIndex * (height / division)
                ymax = (yIndex + 1) * (height / division)

                deleted = run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height)
                total_deleted_all += deleted

    return total_deleted_all, 0.0

def get_first_gap_frame(track):
    frames = sorted([m.frame for m in track.markers])
    print(f"[DEBUG] Analysiere Track: {track.name}, Marker auf Frames: {frames}")
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            cut = frames[i - 1] + 1
            print(f"[DEBUG] → Lücke erkannt in Track '{track.name}' bei Frame {cut}")
            return cut
    if frames:
        print(f"[DEBUG] → Keine Lücke in Track '{track.name}', Rückgabe letzter Frame: {frames[-1]}")
        return frames[-1]
    print(f"[DEBUG] → Track '{track.name}' hat keine Marker.")
    return None


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

def clear_segment_path(context, track, frame, action):
    clip = context.space_data.clip
    scene = context.scene

    for t in clip.tracking.tracks:
        t.select = False
    track.select = True

    scene.frame_current = frame

    try:
        bpy.ops.clip.clear_track_path(action=action)
        print(f"[DEBUG] ✔ clear_track_path für '{track.name}' bei Frame {frame} mit action='{action}'")
    except RuntimeError as e:
        print(f"[WARNUNG] ✖ Fehler bei clear_track_path für '{track.name}': {e}")

def clear_path_on_split_tracks_segmented(context, original_tracks, new_tracks):
    scene = context.scene
    clip = context.space_data.clip

    print("[DEBUG] Starte segmentierten ClearPath-Prozess...")

    clip_editor_area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if not clip_editor_area:
        print("[DEBUG] Kein CLIP_EDITOR gefunden.")
        return

    clip_editor_region = next((r for r in clip_editor_area.regions if r.type == 'WINDOW'), None)
    if not clip_editor_region:
        print("[DEBUG] Keine gültige Region im CLIP_EDITOR gefunden.")
        return

    space = clip_editor_area.spaces.active

    with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=space):

        # ORIGINAL: alles NACH dem Segmentende löschen
        for track in original_tracks:
            segments = get_track_segments(track)
            for seg in segments:
                last = seg[-1]
                clear_segment_path(context, track, last + 1, 'REMAINED')

        # DUPLIKAT: alles VOR dem Segmentbeginn löschen
        for track in new_tracks:
            segments = get_track_segments(track)
            for seg in segments:
                first = seg[0]
                clear_segment_path(context, track, first - 1, 'UPTO')


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        frame_start = scene.frame_start
        frame_end = scene.frame_end

        # 1. Cleanup der fehlerhaften Marker durchführen
        clean_error_tracks(context)

        clip = context.space_data.clip
        tracks = clip.tracking.tracks

        # 2. Tracks mit internen Lücken identifizieren
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            self.report({'INFO'}, "Keine Tracks mit Lücken gefunden.")
            return {'FINISHED'}

        # 3. Namen aller existierenden Tracks merken
        existing_names = {t.name for t in tracks}

        # 4. Nur originale Tracks selektieren
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        # 5. Copy & Paste mit Kontext ausführen
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        with context.temp_override(area=area, region=region, space_data=space):
                            bpy.ops.clip.copy_tracks()
                            bpy.ops.clip.paste_tracks()
                            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                            time.sleep(0.2)


                            # 6. Neue Tracks durch Differenz ermitteln
                            all_names_after = {t.name for t in tracks}
                            new_names = all_names_after - existing_names
                            new_tracks = [t for t in tracks if t.name in new_names]

                            # 7. ClearLogik auf Segmentebene anwenden
                            clear_path_on_split_tracks_segmented(context, original_tracks, new_tracks)

                            self.report({'INFO'}, f"{len(new_tracks)} duplizierte Tracks erkannt und bereinigt.")
                            return {'FINISHED'}

        self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
        return {'CANCELLED'}
