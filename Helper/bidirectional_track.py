# Helper/bidirectional_track.py

import bpy

# Scene Keys – müssen zu tracking_coordinator.py passen:
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

__all__ = (
    "CLIP_OT_bidirectional_track",
    "CLIP_OT_framewise_track",
    "run_framewise_track",
    "register",
    "unregister",
)

# --- NEU: Framewise-Funktion (dein Wunsch) -------------------------------

def run_framewise_track(context, *, backwards=False, max_steps=None) -> dict:
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return {"status": "NO_CLIP", "steps": 0}
    if not any(t.select for t in clip.tracking.tracks):
        return {"status": "NO_SELECTION", "steps": 0}

    scn = context.scene
    fmin, fmax = scn.frame_start, scn.frame_end
    steps = 0

    while True:
        if max_steps is not None and steps >= max_steps:
            return {"status": "FINISHED", "steps": steps}

        cur = scn.frame_current
        if not (fmin <= cur <= fmax):
            return {"status": "FINISHED", "steps": steps}

        res = bpy.ops.clip.track_markers(backwards=backwards, sequence=False)
        if {'CANCELLED'} == set(res):
            return {"status": "CANCELLED", "steps": steps}

        steps += 1
        if scn.frame_current == cur:  # Sicherheitsnetz
            return {"status": "CANCELLED", "steps": steps}


class CLIP_OT_framewise_track(bpy.types.Operator):
    """Trackt selektierte Marker Frame-für-Frame (kein Sequence-Track)."""
    bl_idname = "clip.framewise_track"
    bl_label = "Framewise Track"
    bl_options = {'REGISTER', 'UNDO'}

    backwards: bpy.props.BoolProperty(name="Backwards", default=False)
    max_steps: bpy.props.IntProperty(name="Max Steps (0=∞)", default=0, min=0)

    def execute(self, context):
        max_steps = None if self.max_steps == 0 else self.max_steps
        res = run_framewise_track(context, backwards=self.backwards, max_steps=max_steps)
        self.report({'INFO'}, f"{res}")
        return {'FINISHED'}


# --- WICHTIG: Erwarteter Operator für den Coordinator --------------------
# Minimal-Modaloperator, der die erwarteten Scene-Flags setzt.
# Er kann real dein Bidi-Tracking aufrufen (falls vorhanden) – oder zunächst
# ein NOOP liefern, damit der Coordinator nicht crasht.

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Compatibility-Operator, auf den der Coordinator hört."""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (Compat)"
    bl_options = {'REGISTER', 'UNDO'}

    # Props, die der Coordinator möglicherweise übergibt:
    use_cooperative_triplets: bpy.props.BoolProperty(default=True)
    auto_enable_from_selection: bpy.props.BoolProperty(default=True)

    _timer = None

    def invoke(self, context, event):
        scn = context.scene
        scn[_BIDI_RESULT_KEY] = ""
        scn[_BIDI_ACTIVE_KEY] = True

        # TODO: Hier ggf. deine echte bidi-Logik triggern.
        # Für eine funktionale Minimal-Version machen wir ein kurzes Framewise-Vorwärts-Tracking
        # als Platzhalter, dann beenden wir.
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Beispiel: ein einzelner Step vorwärts, dann fertig
        run_framewise_track(context, backwards=False, max_steps=1)

        # Ergebnis-Flag setzen (hier „DONE“ – oder „NOOP“ falls nichts passiert ist)
        scn = context.scene
        scn[_BIDI_RESULT_KEY] = "DONE"
        scn[_BIDI_ACTIVE_KEY] = False

        # Timer entfernen und beenden
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_framewise_track)
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
    bpy.utils.unregister_class(CLIP_OT_framewise_track)
