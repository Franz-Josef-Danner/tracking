import bpy

# 🧩 Gibt die Marker-Koordinate an einem Frame zurück (oder None)
def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

# 🔍 Prüft, ob zwischen den gesetzten Markern eines Tracks ein Frame-Spalt besteht
def track_has_internal_gaps(track):
    frames = sorted([marker.frame for marker in track.markers])
    if len(frames) < 3:
        return False
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return True
    return False

# 🧼 Löscht Marker mit hohem Bewegungsfehler in einem begrenzten Bildausschnitt
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
        eb = max(vm_diffs) if vm_diffs else 0.0001

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

# 🔍 Gibt ersten Frame **nach** einer Lücke im Track zurück
def find_first_gap_frame(track):
    frames = sorted([m.frame for m in track.markers])
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return frames[i - 1] + 1
    return None

# 🧼 Hauptbereinigungsfunktion mit vollständiger Schleife über alle Fehler- und Gap-Checks
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
        tracks = clip.tracking.tracks

        for track in tracks:
            track.select = False

        width = clip.size[0]
        height = clip.size[1]
        frame_range = (scene.frame_start, scene.frame_end)

        # 1. Fehlerbereinigung in 3 Stufen (groß → klein)
        ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
        fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
        teilfaktoren = [1, 2, 4]

        for stufe in range(3):
            ee = fehlergrenzen[stufe]
            division = teilfaktoren[stufe]
            for xi in range(division):
                for yi in range(division):
                    xmin = xi * (width / division)
                    xmax = (xi + 1) * (width / division)
                    ymin = yi * (height / division)
                    ymax = (yi + 1) * (height / division)
                    run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height)

        # 2. Rekursiver Lücken-Workflow
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

                                new_names = {t.name for t in tracks} - original_names
                                new_tracks = [t for t in tracks if t.name in new_names]
                                for orig, new in zip(tracks_with_gaps, new_tracks):
                                    base = f"pre_{orig.name}"
                                    name = base
                                    i = 1
                                    while name in original_names:
                                        name = f"{base}_{i}"
                                        i += 1
                                    new.name = name
                                    renamed_tracks.append(new)
                                    original_names.add(name)
                                return renamed_tracks
            self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
            return []

        def clear_paths(tracks_with_gaps, duplicates):
            for orig in tracks_with_gaps:
                frame = find_first_gap_frame(orig)
                if frame:
                    orig.select = True
                    scene.frame_current = frame
                    bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=False)
                    orig.select = False
            for dup in duplicates:
                frame = find_first_gap_frame(dup)
                if frame:
                    dup.select = True
                    scene.frame_current = frame
                    bpy.ops.clip.clear_track_path(action='UPTO', clear_active=False)
                    dup.select = False

        loop_count = 0
        max_loops = 20  # Failsafe
        while loop_count < max_loops:
            loop_count += 1
            tracks_with_gaps = [t for t in tracks if track_has_internal_gaps(t) and not t.name.startswith("pre_")]
            if not tracks_with_gaps:
                self.report({'INFO'}, f"✅ Fertig. Kein Track mit Lücken mehr. Schleifen: {loop_count}")
                return {'FINISHED'}

            print(f"🔁 Lücken-Zyklus {loop_count}: {len(tracks_with_gaps)} Tracks mit Gaps")
            duplicates = duplicate_and_rename(tracks_with_gaps)
            if not duplicates:
                self.report({'ERROR'}, "Duplizierung fehlgeschlagen.")
                return {'CANCELLED'}

            clear_paths(tracks_with_gaps, duplicates)

        self.report({'WARNING'}, f"⚠ Maximalanzahl ({max_loops}) erreicht. Vorgang wurde abgebrochen.")
        return {'CANCELLED'}
