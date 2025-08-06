import bpy

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

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

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        clean_error_tracks(context)

        clip = context.space_data.clip
        tracks = clip.tracking.tracks

        for track in tracks:
            track.select = False

        def has_gaps(track):
            frames = sorted([m.frame for m in track.markers])
            return any(b - a > 1 for a, b in zip(frames, frames[1:]))

        selected_tracks = []
        for track in tracks:
            if has_gaps(track):
                track.select = True
                selected_tracks.append(track)

        if not selected_tracks:
            return {'FINISHED'}

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        if not space or not space.clip:
                            continue

                        try:
                            with context.temp_override(area=area, region=region, space_data=space):
                                bpy.ops.clip.copy_tracks()
                                bpy.ops.clip.paste_tracks()

                                copied_names = [track.name for track in selected_tracks]
                                log_msg = f"{len(copied_names)} Tracks mit Lücken wurden dupliziert:\n"
                                log_msg += "\n".join(f"\u2022 {name}" for name in copied_names)

                                self.report({'INFO'}, log_msg)
                                print("[CopyPaste] Duplizierte Tracks:\n" + log_msg)
                                return {'FINISHED'}

                        except Exception as e:
                            self.report({'ERROR'}, f"Copy/Paste Fehler: {str(e)}")
                            return {'CANCELLED'}

        self.report({'ERROR'}, "Kein gültiger Clip Editor für Copy/Paste gefunden.")
        return {'CANCELLED'}
