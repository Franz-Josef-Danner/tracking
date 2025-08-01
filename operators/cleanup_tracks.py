import bpy

def cleanup_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks
    width = clip.size[0]
    height = clip.size[1]

    frame_range = (scene.frame_start, scene.frame_end)
    ee_initial = 10.0
    threshold_factor = 0.9

    # Bereichsdefinitionen
    passes = [
        {"label": "ganzer Bereich", "x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0, "ee_factor": 1.0},
        {"label": "zentral (½)",     "x_min": 0.25, "x_max": 0.75, "y_min": 0.25, "y_max": 0.75, "ee_factor": 0.5},
        {"label": "zentral (¼)",     "x_min": 0.375, "x_max": 0.625, "y_min": 0.375, "y_max": 0.625, "ee_factor": 0.25},
    ]

    def get_marker_position(track, frame):
        for marker in track.markers:
            if marker.frame == frame:
                return marker.co
        return None

    def compute_velocity(p1, p2, p3):
        vx = (p2[0] - p1[0]) + (p3[0] - p2[0])
        vy = (p2[1] - p1[1]) + (p3[1] - p2[1])
        return vx, vy, (vx + vy) / 2

    # Hauptdurchläufe pro Bildausschnitt
    total_deleted = 0
    overall_max_error = 0.0

    for p in passes:
        ee = ee_initial * p["ee_factor"]
        region_deleted = 0
        region_max_error = 0.0

        print(f"\n--- Durchgang: {p['label']} (ee = {ee:.2f}) ---")

        for frame in range(frame_range[0] + 1, frame_range[1] - 1):
            valid_tracks = []
            vm_values = []
            velocities = []

            for track in tracks:
                p1 = get_marker_position(track, frame - 1)
                p2 = get_marker_position(track, frame)
                p3 = get_marker_position(track, frame + 1)
                if not (p1 and p2 and p3):
                    continue
                # Nur Marker im Bildbereich behalten
                if not (p["x_min"] <= p2[0] <= p["x_max"] and p["y_min"] <= p2[1] <= p["y_max"]):
                    continue

                vx, vy, vm = compute_velocity(p1, p2, p3)
                vm_values.append(vm)
                velocities.append((vx, vy))
                valid_tracks.append((track, vx, vy, vm))

            maa = len(valid_tracks)
            if maa == 0:
                continue

            vxa = sum(v[0] for v in velocities) / maa
            vya = sum(v[1] for v in velocities) / maa
            va = (vxa + vya) / 2
            eb = max(abs(vm - va) for (_, _, _, vm) in valid_tracks)
            region_max_error = max(region_max_error, eb)
            overall_max_error = max(overall_max_error, eb)

            print(f"[Frame {frame}] {maa} Marker, Max. Fehler: {eb:.4f}")

            while eb > ee:
                deleted_this_round = 0
                for track, vx, vy, vm in valid_tracks:
                    if abs(vm - va) >= eb:
                        track.select = True
                        deleted_this_round += 1

                if deleted_this_round > 0:
                    bpy.ops.clip.delete_track()
                    print(f"  → {deleted_this_round} Marker gelöscht bei Fehlergrenze {eb:.4f}")
                    total_deleted += deleted_this_round
                    region_deleted += deleted_this_round
                eb *= threshold_factor

        print(f"🧹 Bereich abgeschlossen: {region_deleted} Marker gelöscht. Max. Fehler hier: {region_max_error:.4f}")

    print(f"\n✅ Gesamt gelöscht: {total_deleted} Marker")
    print(f"📈 Höchster Fehler in allen Durchgängen: {overall_max_error:.4f}")

    return total_deleted, overall_max_error


class CLIP_OT_cleanup_tracks(bpy.types.Operator):
    bl_idname = "clip.cleanup_tracks"
    bl_label = "Cleanup Tracks"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip is not None

    def execute(self, context):
        deleted, max_error = cleanup_tracks(context)
        if deleted:
            self.report({'INFO'}, f"{deleted} Marker gelöscht. Max. Fehler: {max_error:.4f}")
        else:
            self.report({'INFO'}, "Keine Marker gelöscht.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)

if __name__ == "__main__":
    register()
