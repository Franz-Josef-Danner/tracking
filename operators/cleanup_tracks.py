import bpy
import math

def cleanup_tracks(context):
    scene = context.scene
    clip = context.space_data.clip
    tracking = clip.tracking
    tracks = tracking.tracks
    width = clip.size[0]
    height = clip.size[1]
    ee = 10.0
    threshold_factor = 0.9

    def get_marker_position(track, frame):
        for marker in track.markers:
            if marker.frame == frame:
                return marker.co
        return None

    def compute_velocity(p1, p2, p3):
        vx = (p2[0] - p1[0]) + (p3[0] - p2[0])
        vy = (p2[1] - p1[1]) + (p3[1] - p2[1])
        return vx, vy, (vx + vy) / 2

    total_deleted = 0  # Zähler für gelöschte Marker insgesamt
    max_error_global = 0.0  # Höchster Fehlerwert im Durchlauf

    def filter_tracks(frame_range, threshold):
        nonlocal total_deleted, max_error_global
        removed = False

        for frame in range(frame_range[0] + 1, frame_range[1] - 1):
            vm_values = []
            velocities = []
            valid_tracks = []
            for track in tracks:
                p1 = get_marker_position(track, frame - 1)
                p2 = get_marker_position(track, frame)
                p3 = get_marker_position(track, frame + 1)
                if p1 and p2 and p3:
                    vx, vy, vm = compute_velocity(p1, p2, p3)
                    vm_values.append(vm)
                    velocities.append((vx, vy))
                    valid_tracks.append((track, vx, vy, vm, p2))

            maa = len(valid_tracks)
            if maa == 0:
                continue

            vxa = sum(v[0] for v in velocities) / maa
            vya = sum(v[1] for v in velocities) / maa
            va = (vxa + vya) / 2
            eb = max(abs(vm - va) for (_, _, _, vm, _) in valid_tracks)
            max_error_global = max(max_error_global, eb)

            print(f"[Frame {frame}] {maa} gültige Marker gefunden. Max. Fehler: {eb:.4f}")

            while eb > threshold:
                deleted_this_loop = 0
                for track, vx, vy, vm, co in valid_tracks:
                    if abs(vm - va) >= eb:
                        track.select = True
                        deleted_this_loop += 1
                        removed = True
                if deleted_this_loop > 0:
                    print(f"  → {deleted_this_loop} Marker zum Löschen selektiert.")
                    total_deleted += deleted_this_loop
                    bpy.ops.clip.delete_track()
                eb *= threshold_factor

        return removed

    frame_range = (scene.frame_start, scene.frame_end)
    bpy.context.scene.frame_set(scene.frame_start)
    if filter_tracks(frame_range, ee):
        print(f"✅ Gesamt gelöschte Marker: {total_deleted}")
        print(f"📈 Maximal festgestellter Fehler: {max_error_global:.4f}")
    else:
        print("ℹ️ Keine Marker gelöscht.")

    return total_deleted, max_error_global


# ---------------------------------------------------------------------
# Operator für den Clip Editor
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Registrierung (für Standalone-Test)
# ---------------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_cleanup_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_tracks)

if __name__ == "__main__":
    register()
