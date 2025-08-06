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
    
        clean_error_tracks(context)

        clip = context.space_data.clip
        tracks = clip.tracking.tracks
    
        # 2. Check tracks with gaps
        original_tracks = [track for track in tracks if track_has_gaps(track, frame_start, frame_end)]
        if not original_tracks:
            self.report({'INFO'}, "Keine Tracks mit Lücken gefunden.")
            return {'FINISHED'}
    
        # 3. Store original names
        original_names = {t.name for t in original_tracks}
        existing_names = {t.name for t in tracks}
        renamed = []
    
        # 4. Select only original_tracks
        for track in tracks:
            track.select = False
        for track in original_tracks:
            track.select = True
    
        # 5. Perform duplication and rename
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        with context.temp_override(area=area, region=region, space_data=space):
                            bpy.ops.clip.copy_tracks()
                            bpy.ops.clip.paste_tracks()
    
                            # Identify new tracks
                            all_names_after = {t.name for t in tracks}
                            new_names = all_names_after - existing_names
                            new_tracks = [t for t in tracks if t.name in new_names]
    
                            # Rename new tracks with prefix
                            for orig, new_track in zip(original_tracks, new_tracks):
                                base_name = f"pre_{orig.name}"
                                name = base_name
                                suffix = 1
                                while name in existing_names:
                                    name = f"{base_name}_{suffix}"
                                    suffix += 1
                                new_track.name = name
                                renamed.append(name)
                                existing_names.add(name)
    
                            self.report({'INFO'}, f"{len(renamed)} duplizierte Tracks:\n" + "\n".join(f"• {r}" for r in renamed))
                            return {'FINISHED'}
    
        self.report({'ERROR'}, "Kein Clip-Editor-Fenster gefunden.")
        return {'CANCELLED'}



        self.report({'ERROR'}, "Kein gültiger Clip Editor für Copy/Paste gefunden.")
        return {'CANCELLED'}
