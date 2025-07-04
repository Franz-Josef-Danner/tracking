import bpy
import math

bl_info = {
    "name": "Dynamic Pattern Tracker",
    "author": "",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "description": "Passt Pattern- und Suchgro\xC3\x9Fen beim Tracking dynamisch an",
}

def dynamic_pattern_tracking():
    clip = None
    for area in bpy.context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            clip = area.spaces.active.clip
            break
    if not clip:
        print("❌ Kein Movie Clip Editor aktiv")
        return

    scene = bpy.context.scene
    start = clip.frame_start
    end = clip.frame_start + clip.frame_duration - 1
    w, h = clip.size

    min_p = 20
    max_p = 100
    print("🚀 Starte dynamische Anpassung der Markergrößen")

    for track in clip.tracking.tracks:
        print(f"\n🎯 Track: {track.name}")
        scene.frame_set(start)

        marker = next((m for m in track.markers if m.frame == start), None)
        if not marker:
            clip.tracking.tracks.active = track
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            marker = next((m for m in track.markers if m.frame == start), None)
        if not marker:
            print("❌ Keine Marker am ersten Frame")
            continue

        last = marker.co.copy()
        for f in range(start + 1, end + 1):
            scene.frame_set(f - 1)
            clip.tracking.tracks.active = track
            bpy.ops.clip.track_markers(backwards=False, sequence=False)
            scene.frame_set(f)

            m = next((x for x in track.markers if x.frame == f), None)
            if not m:
                print(f"⚠️ Marker auf Frame {f} fehlt")
                continue

            dx = abs(m.co.x - last.x) * w
            dy = abs(m.co.y - last.y) * h
            mv = math.sqrt(dx*dx + dy*dy)

            p = max(min(mv, max_p), min_p)
            s = p * 2

            # Update pattern and search areas on the track so Blender uses the
            # new sizes for the next tracking step.
            track.pattern_area[2] = p
            track.pattern_area[3] = p
            track.search_area[2] = s
            track.search_area[3] = s

            print(f"Frame {f}: Bewegung {mv:.1f}px → pattern {p}px, search {s}px")
            last = m.co.copy()

class TRACKING_PT_dynamic_pattern(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Dynamic Pattern Tracker'

    def draw(self, context):
        self.layout.operator("tracking.dynamic_pattern", icon='TRACKING')

class TRACKING_OT_dynamic_pattern(bpy.types.Operator):
    bl_idname = "tracking.dynamic_pattern"
    bl_label = "Track Dynamisch"

    def execute(self, context):
        dynamic_pattern_tracking()
        return {'FINISHED'}


classes = [
    TRACKING_PT_dynamic_pattern,
    TRACKING_OT_dynamic_pattern,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

