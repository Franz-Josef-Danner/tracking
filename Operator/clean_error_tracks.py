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


def find_first_gap_frame(track):
    frames = sorted([m.frame for m in track.markers])
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return frames[i - 1] + 1  # Erster Frame nach der Lücke
    return None


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        tracking = clip.tracking
        tracks = tracking.tracks

        def duplicate_and_rename(tracks_with_gaps):
            original_names = {t.name for t in tracks}
            renamed_tracks = []

            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            space = area.spaces.active
                            with context.temp_override(area=area, region=region, space_data=space):
                                for t in tracks:
                                    t.select = False
                                for t in tracks_with_gaps:
                                    t.select = True
                                bpy.ops.clip.copy_tracks()
                                bpy.ops.clip.paste_tracks()

                                # Neue Namen identifizieren
                                new_names = {t.name for t in tracks} - original_names
                                new_tracks = [t for t in tracks if t.name in new_names]
                                for orig, new in zip(tracks_with_gaps, new_tracks):
                                    base_name = f"pre_{orig.name}"
                                    new_name = base_name
                                    i = 1
                                    while new_name in original_names:
                                        new_name = f"{base_name}_{i}"
                                        i += 1
                                    new.name = new_name
                                    renamed_tracks.append(new)
                                    original_names.add(new_name)
                                return new_tracks
            self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
            return []

        def clear_paths(tracks_with_gaps, duplicate_tracks):
            for orig in tracks_with_gaps:
                frame = find_first_gap_frame(orig)
                if frame:
                    orig.select = True
                    bpy.context.scene.frame_current = frame
                    bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=False)
                    orig.select = False
            for dup in duplicate_tracks:
                frame = find_first_gap_frame(dup)
                if frame:
                    dup.select = True
                    bpy.context.scene.frame_current = frame
                    bpy.ops.clip.clear_track_path(action='UPTO', clear_active=False)
                    dup.select = False

        loop_count = 0
        while True:
            loop_count += 1
            tracks_with_gaps = [t for t in tracks if track_has_internal_gaps(t) and not t.name.startswith("pre_")]
            if not tracks_with_gaps:
                self.report({'INFO'}, f"✅ Fertig. Kein Track mit Lücken mehr. Schleifen: {loop_count}")
                return {'FINISHED'}

            duplicate_tracks = duplicate_and_rename(tracks_with_gaps)
            if not duplicate_tracks:
                self.report({'ERROR'}, "Fehler beim Duplizieren.")
                return {'CANCELLED'}

            clear_paths(tracks_with_gaps, duplicate_tracks)

        return {'FINISHED'}

    
        self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
        return {'CANCELLED'}



        self.report({'ERROR'}, "Kein gültiger Clip Editor für Copy/Paste gefunden.")
        return {'CANCELLED'}
