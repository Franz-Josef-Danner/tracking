import bpy
import time

# Globaler Zustand
bidirectional_track_state = {
    "direction": 'FORWARD',
    "last_marker_count": 0,
    "last_frame": 0,
    "no_change_count": 0,
    "clip": None,
}

def count_selected_markers(clip):
    count = 0
    for track in clip.tracking.tracks:
        if track.select:
            count += len([m for m in track.markers if not m.mute])
    return count

def monitor_tracking():
    state = bidirectional_track_state
    clip = state.get("clip")

    if clip is None:
        print("❌ Kein Clip verfügbar für Tracking-Monitor.")
        return None

    current_marker_count = count_selected_markers(clip)
    current_frame = bpy.context.scene.frame_current

    if (current_marker_count == state["last_marker_count"] and
        current_frame == state["last_frame"]):
        state["no_change_count"] += 1
    else:
        state["no_change_count"] = 0

    state["last_marker_count"] = current_marker_count
    state["last_frame"] = current_frame

    if state["no_change_count"] >= 2:
        if state["direction"] == 'FORWARD':
            print("➡️ Wechsel zu Rückwärts-Tracking")
            state["direction"] = 'BACKWARD'
            state["no_change_count"] = 0
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            return 0.5
        else:
            print("✅ Bidirektionales Tracking abgeschlossen.")
            return None

    return 0.5

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"

    @classmethod
    def poll(cls, context):
        return context.space_data.clip is not None

    def execute(self, context):
        state = bidirectional_track_state
        clip = context.space_data.clip

        state["direction"] = 'FORWARD'
        state["clip"] = clip
        state["last_marker_count"] = count_selected_markers(clip)
        state["last_frame"] = context.scene.frame_current
        state["no_change_count"] = 0

        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        bpy.app.timers.register(monitor_tracking, first_interval=0.5)

        return {'FINISHED'}
