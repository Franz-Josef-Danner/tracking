
import bpy

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None

def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee):
    total_deleted = 0
    eb = 1.0
    frame_start, frame_end = frame_range
    scene = bpy.context.scene

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

            # Check ob der Marker in die Region fällt (p2 = aktuelle Position)
            x, y = p2
            if not (xmin <= x < xmax and ymin <= y < ymax):
                continue

            vxm = (p2[0] - p1[0]) + (p3[0] - p2[0])
            vym = (p2[1] - p1[1]) + (p3[1] - p2[1])
            vm = (vxm + vym) / 2
            marker_data.append((track, vm))

        maa = len(marker_data)
        if maa == 0:
            continue

        va = sum(vm for _, vm in marker_data) / maa
        eb = max(abs(vm - va) for _, vm in marker_data)
        if eb < 0.0001:
            eb = 0.0001

        # Fehlerband iterativ verkleinern
        while eb > ee:
            eb *= 0.9
            for track, vm in marker_data:
                if abs(vm - va) >= eb:
                    track.select = True
                    total_deleted += 1
            bpy.ops.clip.delete_track()

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

    fehlergrenzen = [10, 5, 2.5]
    teilfaktoren = [1, 2, 4]

    total_deleted_all = 0

    for stufe in range(len(fehlergrenzen)):
        ee = fehlergrenzen[stufe] / width  # normalisieren
        division = teilfaktoren[stufe]

        for xIndex in range(division):
            for yIndex in range(division):
                xmin = xIndex * (1.0 / division)
                xmax = (xIndex + 1) * (1.0 / division)
                ymin = yIndex * (1.0 / division)
                ymax = (yIndex + 1) * (1.0 / division)

                deleted = run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee)
                total_deleted_all += deleted

    return total_deleted_all, 0.0


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        deleted, _ = clean_error_tracks(context)
        self.report({'INFO'}, f"Insgesamt {deleted} Marker gelöscht.")
        return {'FINISHED'}
