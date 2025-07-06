bl_info = {
    "name": "Single Frame Tracker",
    "blender": (4, 0, 0),
    "category": "Clip",
    "description": "Adds a button to track selected markers for one frame",
}

import bpy

class CLIP_OT_track_one_frame(bpy.types.Operator):
    """Track selected markers forward by one frame until they can't move further"""
    bl_idname = "clip.track_one_frame"
    bl_label = "Track Until Done"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        max_iterations = 1000
        iterations = 0

        print("[Track Until Done] Starting frame-by-frame tracking...")

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
                    if not space:
                        continue
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region, space_data=space):
                                clip = space.clip
                                if not clip:
                                    print("[Track Until Done] No clip loaded.")
                                    continue

                                clip_user = space.clip_user
                                frame = clip_user.frame_current
                                bpy.context.scene.frame_set(frame)

                                while iterations < max_iterations:
                                    active_tracks = [
                                        t
                                        for t in clip.tracking.tracks
                                        if t.select and not getattr(t, "mute", False)
                                    ]
                                    if not active_tracks:
                                        print(f"[Track Until Done] No active markers left at frame {frame}.")
                                        break

                                    print(f"[Track Until Done] Frame {frame}, active markers: {len(active_tracks)}")
                                    result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
                                    print(f"[Track Until Done] Result: {result}")

                                    if 'CANCELLED' in result:
                                        print(f"[Track Until Done] Tracking cancelled at frame {frame}.")
                                        break

                                    frame += 1
                                    bpy.context.scene.frame_set(frame)
                                    iterations += 1

                                print(f"[Track Until Done] Finished at frame {frame} after {iterations} steps.")
                                self.report({'INFO'}, f"Tracking completed in {iterations} steps.")
                                return {'FINISHED'}

        print("[Track Until Done] No Clip Editor found.")
        self.report({'WARNING'}, "No suitable Clip Editor context found.")
        return {'CANCELLED'}


class CLIP_PT_one_frame_tracker_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking"
    bl_label = "One Frame Tracker"

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.track_one_frame", text="Track Until Done")


def register():
    bpy.utils.register_class(CLIP_OT_track_one_frame)
    bpy.utils.register_class(CLIP_PT_one_frame_tracker_panel)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_track_one_frame)
    bpy.utils.unregister_class(CLIP_PT_one_frame_tracker_panel)


if __name__ == "__main__":
    register()
    bpy.ops.wm.console_toggle()
