import bpy

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

def track_has_internal_gaps(track):
    frames = sorted([marker.frame for marker in track.markers])
    if len(frames) < 3:
        return False
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return True
    return False

def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    total_deleted = 0
    frame_start, frame_end = frame_range
    for fi in range(frame_start + 1, frame_end - 1):
        f1, f2 = fi - 1, fi + 1
        marker_data = []
        for track in tracks:
            p1, p2, p3 = get_marker_position(track, f1), get_marker_position(track, fi), get_marker_position(track, f2)
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

def find_first_gap_frame(track):
    frames = sorted([marker.frame for marker in track.markers])
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] > 1:
            return frames[i - 1] + 1
    return None

def clean_error_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracks = clip.tracking.tracks

    for track in tracks:
        track.select = False

    width, height = clip.size
    frame_range = (scene.frame_start, scene.frame_end)
    ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
    fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
    teilfaktoren = [1, 2, 4]

    for stufe in range(len(fehlergrenzen)):
        ee = fehlergrenzen[stufe]
        division = teilfaktoren[stufe]
        for xIndex in range(division):
            for yIndex in range(division):
                xmin = xIndex * (width / division)
                xmax = (xIndex + 1) * (width / division)
                ymin = yIndex * (height / division)
                ymax = (yIndex + 1) * (height / division)
                run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height)

def duplicate_and_clear_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracks = clip.tracking.tracks
    existing_names = {t.name for t in tracks}

    loop_count = 0
    while True:
        loop_count += 1
        orig_tracks = [t for t in tracks if track_has_internal_gaps(t) and not t.name.startswith("pre_")]
        if not orig_tracks:
            return loop_count

        # Clear Selection
        for t in tracks:
            t.select = False
        for t in orig_tracks:
            t.select = True

        new_tracks = []
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        with context.temp_override(area=area, region=region, space_data=space):
                            bpy.ops.clip.copy_tracks()
                            bpy.ops.clip.paste_tracks()

                            new_names = {t.name for t in tracks} - existing_names
                            new_tracks = [t for t in tracks if t.name in new_names]
                            for orig, new in zip(orig_tracks, new_tracks):
                                base_name = f"pre_{orig.name}"
                                name = base_name
                                count = 1
                                while name in existing_names:
                                    name = f"{base_name}_{count}"
                                    count += 1
                                new.name = name
                                existing_names.add(name)
                            break

        # Clear Paths:
        for orig in orig_tracks:
            gap_frame = find_first_gap_frame(orig)
            if gap_frame:
                orig.select = True
                scene.frame_current = gap_frame
                bpy.ops.clip.clear_track_path(action='REMAINED', clear_active=False)
                orig.select = False

        for dup in new_tracks:
            gap_frame = find_first_gap_frame(dup)
            if gap_frame:
                dup.select = True
                scene.frame_current = gap_frame
                bpy.ops.clip.clear_track_path(action='UPTO', clear_active=False)
                dup.select = False

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        clean_error_tracks(context)
        loops = duplicate_and_clear_tracks(context)
        self.report({'INFO'}, f"✅ Fertig. Schleifendurchläufe: {loops}")
        return {'FINISHED'}
