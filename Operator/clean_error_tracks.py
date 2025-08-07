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
                        marker = track.markers.find_frame(f)
                        if marker:
                            track.markers.delete(marker)
                            total_deleted += 1

    return total_deleted


def clean_error_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks

    for track in tracks:
        track.select = False

    width, height = clip.size
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

                deleted = run_cleanup_in_region(
                    tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height
                )
                total_deleted_all += deleted

    return total_deleted_all


def get_clip_editor_context(context):
    for area in context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    space = area.spaces.active
                    return {
                        "window": context.window,
                        "area": area,
                        "region": region,
                        "space_data": space
                    }
    return None


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        deleted = clean_error_tracks(context)

        clip = context.space_data.clip
        tracks = clip.tracking.tracks

        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            self.report({'INFO'}, f"{deleted} Marker gelöscht. Keine Lücken gefunden.")
            return {'FINISHED'}

        before = set(tracks)

        for track in tracks:
            track.select = False
        for track in original_tracks:
            track.select = True

        override_ctx = get_clip_editor_context(context)
        if not override_ctx:
            self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
            return {'CANCELLED'}

        with context.temp_override(**override_ctx):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()

        after = set(clip.tracking.tracks)
        new_tracks = list(after - before)

        renamed = []
        existing_names = {t.name for t in before}
        for orig, new in zip(original_tracks, new_tracks):
            base_name = f"pre_{orig.name}"
            name = base_name
            suffix = 1
            while name in existing_names:
                name = f"{base_name}_{suffix}"
                suffix += 1
            new.name = name
            renamed.append(name)
            existing_names.add(name)

        self.report({'INFO'}, f"{deleted} Marker gelöscht.\n{len(renamed)} duplizierte Tracks:\n" +
                     "\n".join(f"• {r}" for r in renamed))
        return {'FINISHED'}
