import bpy

bl_info = {
    "name": "Track Until Stop",
    "description": "Trackt ausgewaehlte Marker Frame fuer Frame, bis keiner mehr aktiv ist",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar > Tracking",
    "category": "Tracking",
}


def track_until_stop(ctx):
    """Track selected markers frame by frame until none remain active."""
    area = ctx.area
    if not area or area.type != "CLIP_EDITOR":
        print("track_until_stop: \u274c Kein Movie Clip Editor aktiv")
        return

    clip = area.spaces.active.clip
    if not clip:
        print("track_until_stop: \u274c Kein Clip geladen")
        return

    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("track_until_stop: \u274c Kein Marker ausgew\xe4hlt")
        return

    scene = ctx.scene
    start_frame = scene.frame_current
    active = tracks[:]
    iteration = 0

    while active:
        iteration += 1
        frame = scene.frame_current
        print(f"track_until_stop: Iteration {iteration} bei Frame {frame}")

        # Use a stable context override so track_markers gets the correct area,
        # region and space data. The last region is not always the window.
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            print("track_until_stop: \u274c Keine WINDOW-Region gefunden")
            break
        override = ctx.copy()
        override["area"] = area
        override["region"] = region
        override["space_data"] = area.spaces.active
        override["clip"] = clip
        result = bpy.ops.clip.track_markers(override, backwards=False, sequence=False)
        print(f"track_markers result: {result}")

        next_f = frame + 1
        survivors = []
        for t in active:
            if t.markers.find_frame(next_f):
                survivors.append(t)
            else:
                print(f"  {t.name}: kein Marker auf Frame {next_f} -> entfernt")
                t.select = False
        active = survivors
        if active:
            scene.frame_set(next_f)

    scene.frame_set(start_frame)
    print("track_until_stop: \u2b50 Tracking beendet")


class TRACKING_OT_track_until_stop(bpy.types.Operator):
    bl_idname = "tracking.track_until_stop"
    bl_label = "Track Until Stop"
    bl_description = (
        "Trackt ausgew\xe4hlte Marker frameweise, bis keiner mehr aktiv ist"
    )

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return (
            space is not None
            and space.type == "CLIP_EDITOR"
            and getattr(space, "clip", None)
        )

    def execute(self, context):
        track_until_stop(context)
        return {'FINISHED'}


class TRACKING_PT_track_until_stop(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Track Until Stop'

    def draw(self, context):
        self.layout.operator(
            TRACKING_OT_track_until_stop.bl_idname, icon='TRACKING_FORWARDS'
        )


classes = [TRACKING_OT_track_until_stop, TRACKING_PT_track_until_stop]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
