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

    def filter_tracks(frame_range, threshold):
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
                    velocities.append((track, vm))
                    valid_tracks.append((track, vx, vy, vm, p2))

            if not vm_values:
                continue

            vxa = sum(v[1] for v in velocities) / len(velocities)
            vya = sum(v[2] for v in velocities) / len(velocities)
            va = (vxa + vya) / 2
            eb = max(abs(vm - va) for (_, _, _, vm, _) in valid_tracks)

            while eb > threshold:
                for track, vx, vy, vm, co in valid_tracks:
                    if abs(vm - va) >= eb:
                        track.select = True
                        removed = True
                bpy.ops.clip.delete_track()
                eb *= threshold_factor
        return removed

    frame_range = (scene.frame_start, scene.frame_end)
    bpy.context.scene.frame_set(scene.frame_start)
    if filter_tracks(frame_range, ee):
        print("Tracks bereinigt.")

# Optional: als Operator, wenn du es mit Button verknüpfen willst
class CLIP_OT_cleanup_motion_tracks(bpy.types.Operator):
    bl_idname = "clip.cleanup_motion_tracks"
    bl_label = "Cleanup Motion Tracks"

    @classmethod
    def poll(cls, context):
        return context.space_data.clip is not None

    def execute(self, context):
        cleanup_tracks(context)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CLIP_OT_cleanup_motion_tracks)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_cleanup_motion_tracks)

if __name__ == "__main__":
    register()
