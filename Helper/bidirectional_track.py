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
- **Wichtig gegen "Frame springt zurück / ab Frame 4 Reset"**:
  Wir steuern **space.clip_user.frame_current** im Movie-Clip-Editor und rufen
  die Operatoren mit Context-Override des CLIP_EDITORs auf. Außerdem validieren wir
  nach jedem Step, ob der Frame wirklich gewechselt hat – falls nicht, wird der
  Frame manuell um ±1 weitergestellt. Zusätzlich: Bei CANCELLED oder No-Progress
  versuchen wir einen erneuten Step, bevor wir endgültig abbrechen.
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

def _find_clip_area_ctx(context: bpy.types.Context) -> Optional[dict]:
    win = context.window
    if not win:
        return None
    screen = win.screen
    if not screen:
        return None
    for area in screen.areas:
        if getattr(area, "type", None) == 'CLIP_EDITOR':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if not region:
                continue
            space = area.spaces.active
            if getattr(space, "clip", None) is None:
                try:
                    space.clip = bpy.data.movieclips[0] if bpy.data.movieclips else None
                except Exception:
                    pass
            return {
                "window": win,
                "screen": screen,
                "area": area,
                "region": region,
                "space_data": space,
                "scene": context.scene,
            }
    return None


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


def _clip_frame_range(clip: bpy.types.MovieClip) -> tuple[int, int]:
    try:
        f0 = int(clip.frame_start)
        dur = int(clip.frame_duration)
        if dur > 0:
            return f0, f0 + dur - 1
    except Exception:
        pass
    scn = bpy.context.scene
    return int(scn.frame_start), int(scn.frame_end)


def _bump_frame(space: bpy.types.SpaceClip, *, backwards: bool) -> None:
    try:
        user = space.clip_user
        user.frame_current += (-1 if backwards else 1)
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Framewise Tracking – Kernfunktion
# ----------------------------------------------------------------------------

def run_framewise_track(
    context: bpy.types.Context,
    *,
    backwards: bool = False,
    max_steps: Optional[int] = None,
    retry_on_cancelled: bool = True,
    retry_on_no_progress: bool = True,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Trackt selektierte Marker **frameweise** und robust gegen Frame-Drift.

    - Verwendet CLIP_EDITOR-Context-Override.
    - Liest/setzt **space.clip_user.frame_current** statt nur scene.frame_current.
    - Verifiziert nach jedem Step den Framewechsel; bei Problemen optional **Retry**
      mit manuellem Frame-Bump (±1), bis *max_retries* erreicht sind.

    Parameters
    ----------
    backwards : bool
        Richtung (False=vorwärts, True=rückwärts)
    max_steps : int | None
        Sicherheitslimit der Schritte (None = unbegrenzt)
    retry_on_cancelled : bool
        Bei {'CANCELLED'} vom Operator erneut probieren (mit Bump)
    retry_on_no_progress : bool
        Wenn Frame nicht wechselt, erneut probieren (mit Bump)
    max_retries : int
        Max. Retries **pro Schritt**, bevor abgebrochen wird
    """
    ov = _find_clip_area_ctx(context)
    if ov is None:
        return {"status": "NO_CLIP", "steps": 0}

    space = ov["space_data"]
    clip = getattr(space, "clip", None)
    if clip is None:
        clip = _get_active_clip(context)
        if clip is None:
            return {"status": "NO_CLIP", "steps": 0}
        try:
            space.clip = clip
        except Exception:
            pass

    if not _has_selected_tracks(clip):
        return {"status": "NO_SELECTION", "steps": 0}

    fmin, fmax = _clip_frame_range(clip)

    def _clamp_user_frame():
        try:
            u = space.clip_user
            if u.frame_current < fmin:
                u.frame_current = fmin
            elif u.frame_current > fmax:
                u.frame_current = fmax
        except Exception:
            pass

    steps = 0
    with bpy.context.temp_override(**ov):
        user = space.clip_user
        _clamp_user_frame()
        while True:
            if max_steps is not None and steps >= int(max_steps):
                return {"status": "FINISHED", "steps": steps}

            cur = int(user.frame_current)
            if cur < fmin or cur > fmax:
                return {"status": "FINISHED", "steps": steps}

            # --- versuche EINEN Schritt, mit optionalen Retries ---
            retries = 0
            while True:
                # Single-Step Tracking (kein sequence)
                result = bpy.ops.clip.track_markers(backwards=backwards, sequence=False)
                if {'CANCELLED'} == set(result):
                    if retry_on_cancelled and retries < int(max_retries):
                        retries += 1
                        _bump_frame(space, backwards=backwards)
                        _clamp_user_frame()
                        continue
                    # keine weiteren Versuche
                    return {"status": "CANCELLED", "steps": steps}

                # Schritt war formal erfolgreich → prüfen, ob Frame wechselte
                new_cur = int(user.frame_current)
                if new_cur == cur:
                    if retry_on_no_progress and retries < int(max_retries):
                        retries += 1
                        _bump_frame(space, backwards=backwards)
                        _clamp_user_frame()
                        # Wiederhole den Versuch: ggf. hilft der Bump, den Clip voranzuschalten
                        continue
                    # Kein Fortschritt trotz Retries → abbrechen
                    return {"status": "CANCELLED", "steps": steps}

                # Fortschritt! Schritt gezählt, äußere Schleife fortsetzen
                steps += 1
                break

# ----------------------------------------------------------------------------
# Operator: Framewise Track
# ----------------------------------------------------------------------------

class CLIP_OT_framewise_track(bpy.types.Operator):
    bl_idname = "clip.framewise_track"
    bl_label = "Framewise Track"
    bl_options = {"REGISTER", "UNDO"}

    backwards: bpy.props.BoolProperty(default=False)
    max_steps: bpy.props.IntProperty(default=0, min=0)

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
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (Compat)"
    bl_options = {"REGISTER", "UNDO"}

    use_cooperative_triplets: bpy.props.BoolProperty(default=True)
    auto_enable_from_selection: bpy.props.BoolProperty(default=True)
    steps_per_tick: bpy.props.IntProperty(default=1, min=1, max=32)

    _timer: Optional[bpy.types.Timer] = None
    _ran_any_step: bool = False

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
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

        ov = _find_clip_area_ctx(context)
        if ov is None:
            return self._finish(context, result="NOOP")
        with bpy.context.temp_override(**ov):
            clip = _get_active_clip(bpy.context)
            if not _has_selected_tracks(clip):
                return self._finish(context, result="NOOP")

            did_steps = 0
            for _ in range(int(self.steps_per_tick)):
                r1 = run_framewise_track(bpy.context, backwards=False, max_steps=1)
                did_steps += int(r1.get("steps", 0))
                r2 = run_framewise_track(bpy.context, backwards=True, max_steps=1)
                did_steps += int(r2.get("steps", 0))

        self._ran_any_step = self._ran_any_step or (did_steps > 0)
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
