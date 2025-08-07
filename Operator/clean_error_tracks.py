import bpy
import time

from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented
from ..Helper.mute_invalid_segments import mute_invalid_segments, remove_segment_boundary_keys

# ---------- interne Helfer ----------

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    return marker.co if marker else None

def track_has_internal_gaps(track):
    frames = sorted(m.frame for m in track.markers)
    if len(frames) < 3:
        return False
    return any(frames[i] - frames[i - 1] > 1 for i in range(1, len(frames)))

def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    total_deleted = 0
    fstart, fend = frame_range

    for fi in range(fstart + 1, fend - 1):
        f1, f2 = fi - 1, fi + 1
        md = []

        for tr in tracks:
            p1 = get_marker_position(tr, f1)
            p2 = get_marker_position(tr, fi)
            p3 = get_marker_position(tr, f2)
            if not (p1 and p2 and p3):
                continue

            x, y = p2[0] * width, p2[1] * height
            if not (xmin <= x < xmax and ymin <= y < ymax):
                continue

            vxm = (p2[0] - p1[0]) + (p3[0] - p2[0])
            vym = (p2[1] - p1[1]) + (p3[1] - p2[1])
            md.append((tr, vxm, vym))

        if not md:
            continue

        vxa = sum(vx for _, vx, _ in md) / len(md)
        vya = sum(vy for _, _, vy in md) / len(md)
        va = (vxa + vya) / 2

        eb = max([abs((vx + vy) / 2 - va) for _, vx, vy in md], default=0.0001)
        eb = max(eb, 0.0001)

        while eb > ee:
            eb *= 0.95
            for tr, vx, vy in md:
                vm = (vx + vy) / 2
                if abs(vm - va) >= eb:
                    for f in (f1, fi, f2):
                        if tr.markers.find_frame(f):
                            tr.markers.delete_frame(f)
                            total_deleted += 1

    return total_deleted

def clean_error_tracks(context, space):
    scene = context.scene
    clip = space.clip
    tracks = clip.tracking.tracks

    for t in tracks:
        t.select = False

    width, height = clip.size
    frame_range = (scene.frame_start, scene.frame_end)

    ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
    thresholds = [ee_base, ee_base / 2, ee_base / 4]
    divisions = [1, 2, 4]

    tot = 0
    for ee, div in zip(thresholds, divisions):
        for xi in range(div):
            for yi in range(div):
                xmin = xi * (width / div)
                xmax = (xi + 1) * (width / div)
                ymin = yi * (height / div)
                ymax = (yi + 1) * (height / div)
                tot += run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height)
    return tot, 0.0

# ---------- Operator ----------

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        area = region = space = None

        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area, region, space = a, r, a.spaces.active

        if not space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # 1) Fehlerbereinigung (grid)
        clean_error_tracks(context, space)
        clip = space.clip
        tracks = clip.tracking.tracks

        # 2) Tracks mit internen Gaps duplizieren & Splitting-Mute anwenden
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if original_tracks:
            existing = {t.name for t in tracks}
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

            all_after = {t.name for t in tracks}
            new_names = all_after - existing
            new_tracks = [t for t in tracks if t.name in new_names]

            clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks)

        # 3) HART: Keys exakt auf Segment-/Trackgrenzen entfernen
        remove_segment_boundary_keys(list(tracks), only_if_keyed=True, also_track_bounds=True)

        # 4) Weich: alles Ungültige muten (statt löschen). Bei Bedarf action="delete".
        mute_invalid_segments(list(tracks), scene.frame_end, action="mute")

        return {'FINISHED'}
