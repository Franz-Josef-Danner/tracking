# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/bidirectional_track.py

Enthält:
- run_framewise_track(): Utility, die selektierte Marker **Frame für Frame** trackt
  (kein Sequence-Tracking, kein Setzen/Neuplazieren), bis die Szenenrange endet
  oder Blender keine Schritte mehr machen kann.
- CLIP_OT_framewise_track: Komfort-Operator für run_framewise_track().
- CLIP_OT_bidirectional_track: Kompatibilitäts-/Brücken-Operator, den der
  tracking_coordinator erwartet. Setzt die Scene-Flags, läuft modal und beendet
  sich mit einem Ergebnis-Flag. Implementiert hier eine einfache Bi-Schrittkette
  (1x vorwärts, 1x rückwärts als Minimalfall), kann später leicht durch die
  „echte“ Bidirectional-Logik ersetzt werden.

Hinweis:
- Die vom Coordinator verwendeten Scene-Keys müssen exakt übereinstimmen.
"""

from __future__ import annotations
import bpy
from typing import Optional, Dict, Any

# --- Scene Keys (müssen zu tracking_coordinator.py passen) --------------------
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"

__all__ = (
    "run_framewise_track",
    "CLIP_OT_framewise_track",
    "CLIP_OT_bidirectional_track",
    "register",
    "unregister",
)


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'CLIP_EDITOR' and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _has_selected_tracks(clip: Optional[bpy.types.MovieClip]) -> bool:
    if clip is None:
        return False
    try:
        return any(t.select for t in clip.tracking.tracks)
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Framewise Tracking – Kernfunktion
# ----------------------------------------------------------------------------

def run_framewise_track(
    context: bpy.types.Context,
    *,
    backwards: bool = False,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Trackt selektierte Marker **frameweise** bis Ende/Abbruch.

    Parameters
    ----------
    backwards: bool
        False = vorwärts, True = rückwärts.
    max_steps: int | None
        Sicherheitslimit für Einzelschritte; None = unbegrenzt.

    Returns
    -------
    dict
        {"status": "FINISHED"|"CANCELLED"|"NO_SELECTION"|"NO_CLIP", "steps": int}
    """
    clip = _get_active_clip(context)
    if clip is None:
        return {"status": "NO_CLIP", "steps": 0}
    if not _has_selected_tracks(clip):
        return {"status": "NO_SELECTION", "steps": 0}

    scene = context.scene
    frame_min = int(scene.frame_start)
    frame_max = int(scene.frame_end)

    steps = 0
    while True:
        if max_steps is not None and steps >= int(max_steps):
            return {"status": "FINISHED", "steps": steps}

        cur = int(scene.frame_current)
        if cur < frame_min or cur > frame_max:
            return {"status": "FINISHED", "steps": steps}

        # WICHTIG: sequence=False erzwingt Single-Step-Tracking
        res = bpy.ops.clip.track_markers(backwards=backwards, sequence=False)
        if {'CANCELLED'} == set(res):
            return {"status": "CANCELLED", "steps": steps}

        steps += 1

        # Sicherheitsnetz: falls der Frame nicht wechselt, abbrechen
        if int(scene.frame_current) == cur:
            return {"status": "CANCELLED", "steps": steps}


# ----------------------------------------------------------------------------
# Operator: Framewise Track
# ----------------------------------------------------------------------------

class CLIP_OT_framewise_track(bpy.types.Operator):
    """Trackt selektierte Marker Frame-für-Frame (kein Sequence-Track)."""

    bl_idname = "clip.framewise_track"
    bl_label = "Framewise Track"
    bl_options = {"REGISTER", "UNDO"}

    backwards: bpy.props.BoolProperty(  # type: ignore
        name="Backwards",
        description="Rückwärts tracken",
        default=False,
    )
    max_steps: bpy.props.IntProperty(  # type: ignore
        name="Max Steps (0=unbegrenzt)",
        description="Sicherheitslimit für Einzelschritte",
        default=0,
        min=0,
    )

    def execute(self, context: bpy.types.Context):
        max_steps = None if self.max_steps == 0 else int(self.max_steps)
        result = run_framewise_track(
            context,
            backwards=bool(self.backwards),
            max_steps=max_steps,
        )
        self.report({'INFO'}, f"FramewiseTrack: {result}")
        return {'FINISHED'}


# ----------------------------------------------------------------------------
# Operator: Bidirectional Track (Kompatibilität für Coordinator)
# ----------------------------------------------------------------------------

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Minimaler, kompatibler Bidirectional-Operator.

    Setzt die erwarteten Scene-Flags und läuft modal. Als Platzhalter führt er
    je einen Framewise-Schritt vorwärts und rückwärts aus. Später einfach durch
    die echte Bi-Tracking-Logik ersetzen.
    """

    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (Compat)"
    bl_options = {"REGISTER", "UNDO"}

    # Props, die vom Coordinator evtl. übergeben werden
    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Use Cooperative Triplets",
        default=True,
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Auto Enable From Selection",
        default=True,
    )

    # Optional: wie viele Schritte je Tick ausführen
    steps_per_tick: bpy.props.IntProperty(  # type: ignore
        name="Steps per Tick",
        default=1,
        min=1,
        max=32,
    )

    _timer: Optional[bpy.types.Timer] = None
    _ran_any_step: bool = False

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Coordinator ruft im CLIP_EDITOR auf – wir halten das bei.
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        scn = context.scene
        scn[_BIDI_RESULT_KEY] = ""
        scn[_BIDI_ACTIVE_KEY] = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.02, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context: bpy.types.Context, *, result: str):
        scn = context.scene
        scn[_BIDI_RESULT_KEY] = str(result).upper()
        scn[_BIDI_ACTIVE_KEY] = False
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        return {'FINISHED'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        clip = _get_active_clip(context)
        if not _has_selected_tracks(clip):
            # Nichts zu tun → NOOP
            return self._finish(context, result="NOOP")

        # Minimaler bidi-Zyklus: vorwärts- und rückwärts-Einzelschritt
        did_steps = 0
        for _ in range(int(self.steps_per_tick)):
            r1 = run_framewise_track(context, backwards=False, max_steps=1)
            did_steps += int(r1.get("steps", 0))
            r2 = run_framewise_track(context, backwards=True, max_steps=1)
            did_steps += int(r2.get("steps", 0))

        self._ran_any_step = self._ran_any_step or (did_steps > 0)

        # In dieser Platzhalter-Variante beenden wir direkt nach einem Tick
        return self._finish(context, result=("DONE" if self._ran_any_step else "NOOP"))


# ----------------------------------------------------------------------------
# Register API
# ----------------------------------------------------------------------------

def register() -> None:
    bpy.utils.register_class(CLIP_OT_framewise_track)
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister() -> None:
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
    bpy.utils.unregister_class(CLIP_OT_framewise_track)
