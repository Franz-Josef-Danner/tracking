# Helper/bidirectional_track.py

import bpy

__all__ = (
    "run_framewise_track",
    "CLIP_OT_framewise_track",
    "register",
    "unregister",
)


def run_framewise_track(
    context,
    backwards: bool = False,
    max_steps: int | None = None,
) -> dict:
    """
    Trackt selektierte Marker Frame-für-Frame, bis kein Frame mehr verfügbar ist
    oder der Operator clip.track_markers abbricht.

    Parameters
    ----------
    backwards : bool
        True = rückwärts, False = vorwärts.
    max_steps : int | None
        Sicherheitslimit für die Anzahl Schritte. None = unbegrenzt.

    Returns
    -------
    dict
        {"status": "FINISHED"|"CANCELLED"|"NO_SELECTION"|"NO_CLIP",
         "steps": int}
    """
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return {"status": "NO_CLIP", "steps": 0}
    if not any(t.select for t in clip.tracking.tracks):
        return {"status": "NO_SELECTION", "steps": 0}

    scene = context.scene
    frame_min = scene.frame_start
    frame_max = scene.frame_end

    steps = 0
    while True:
        if max_steps is not None and steps >= max_steps:
            return {"status": "FINISHED", "steps": steps}

        cur = scene.frame_current
        if not (frame_min <= cur <= frame_max):
            return {"status": "FINISHED", "steps": steps}

        # eigentlicher Step (kein Sequence-Tracking!)
        res = bpy.ops.clip.track_markers(
            backwards=backwards,
            sequence=False,
        )
        if {'CANCELLED'} == set(res):
            return {"status": "CANCELLED", "steps": steps}

        steps += 1
        if scene.frame_current == cur:
            # Sicherheit: Frame hat sich nicht bewegt ⇒ Ende
            return {"status": "CANCELLED", "steps": steps}


class CLIP_OT_framewise_track(bpy.types.Operator):
    """Trackt selektierte Marker Frame-für-Frame"""
    bl_idname = "clip.framewise_track"
    bl_label = "Framewise Track"
    bl_options = {"REGISTER", "UNDO"}

    backwards: bpy.props.BoolProperty(
        name="Backwards",
        description="Rückwärts tracken",
        default=False,
    )
    max_steps: bpy.props.IntProperty(
        name="Max Steps (0=unbegrenzt)",
        default=0,
        min=0,
    )

    def execute(self, context):
        max_steps = None if self.max_steps == 0 else self.max_steps
        result = run_framewise_track(
            context,
            backwards=self.backwards,
            max_steps=max_steps,
        )
        self.report({'INFO'}, f"FramewiseTrack: {result}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_framewise_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_framewise_track)
