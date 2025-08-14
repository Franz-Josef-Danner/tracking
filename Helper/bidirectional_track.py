# Helper/bidirectional_track.py
import bpy

from .solve_camera import solve_watch_clean
from .clean_short_tracks import clean_short_tracks
from .find_low_marker_frame import run_find_low_marker_frame  # ← NEU: Handoff-Ziel importieren

__all__ = ("run_bidirectional_track",)

def _clip_override(context):
    win = getattr(context, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

def _get_space_clip(ctx):
    space = getattr(ctx, "space_data", None)
    return getattr(space, "clip", None) if space else None

def _ensure_active_clip(ctx):
    """
    Liefert einen nutzbaren MovieClip und setzt – falls möglich – den CLIP_EDITOR
    in den TRACKING-Mode mit gesetztem Clip.
    """
    clip = _get_space_clip(ctx)
    if clip:
        return clip

    # Fallback: ersten verfügbaren MovieClip verwenden
    try:
        fallback_clip = next(iter(bpy.data.movieclips))
    except StopIteration:
        print("Kein MovieClip im Blendfile vorhanden.")
        return None

    ov = _clip_override(ctx)
    if ov:
        try:
            with ctx.temp_override(**ov):
                ov['space_data'].clip = fallback_clip
                try:
                    ov['space_data'].mode = 'TRACKING'
                except Exception:
                    pass
            print(f"[Tracking] Fallback-Clip gesetzt: {fallback_clip.name}")
        except Exception as e:
            print(f"[Tracking] Konnte Fallback-Clip nicht im UI setzen: {e}")

    return fallback_clip

def _run_forward_track(ctx):
    print("→ Starte Vorwärts-Tracking...")
    ov = _clip_override(ctx)
    if ov:
        with ctx.temp_override(**ov):
            try:
                ov['space_data'].mode = 'TRACKING'
            except Exception:
                pass
            return bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
    return bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

def _run_backward_track(ctx):
    print("→ Starte Rückwärts-Tracking...")
    ov = _clip_override(ctx)
    if ov:
        with ctx.temp_override(**ov):
            try:
                ov['space_data'].mode = 'TRACKING'
            except Exception:
                pass
            return bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
    return bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)

def _clean_short_tracks(ctx):
    ov = _clip_override(ctx)
    if ov:
        with ctx.temp_override(**ov):
            try:
                ov['space_data'].mode = 'TRACKING'
            except Exception:
                pass
            return bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
    return bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')

def run_bidirectional_track(context):
    """
    Step 0: Vorwärts-Tracking
    Step 1: Reset auf Start-Frame
    Step 2: eine Schleife warten
    Step 3: Rückwärts-Tracking
    Step 4: Stabilitätsprüfung; bei Stabilität -> clean_short_tracks → Handoff an run_find_low_marker_frame
    """
    state = {
        "step": 0,
        "start_frame": int(getattr(context.scene, "frame_current", 1)),
        "prev_marker_count": -1,
        "prev_frame": -1,
        "stable_count": 0,
        "active": True,
    }

    print("[Tracking] Schritt: 0")

    def _stop():
        state["active"] = False

    def _stability_tick(ctx, clip):
        current_frame = ctx.scene.frame_current
        try:
            current_marker_count = sum(len(t.markers) for t in clip.tracking.tracks)
        except Exception:
            current_marker_count = 0

        if (state["prev_marker_count"] == current_marker_count and
                state["prev_frame"] == current_frame):
            state["stable_count"] += 1
        else:
            state["stable_count"] = 0

        state["prev_marker_count"] = current_marker_count
        state["prev_frame"] = current_frame

        print(f"[Tracking-Stabilität] Frame: {current_frame}, Marker: {current_marker_count}, Stabil: {state['stable_count']}/2")
        
    def _tick():
        if not state["active"]:
            return None  # Timer beenden

        ctx = bpy.context
        clip = _ensure_active_clip(ctx)
        if clip is None:
            print("Kein aktiver Clip im Tracking-Editor gefunden.")
            _stop()
            return None

        step = state["step"]

        if step == 0:
            _run_forward_track(ctx)
            state["step"] = 1
            return 0.5

        elif step == 1:
            print("→ Warte auf Abschluss des Vorwärts-Trackings...")
            ctx.scene.frame_current = state["start_frame"]
            print(f"← Frame zurückgesetzt auf {state['start_frame']}")
            state["step"] = 2
            return 0.5

        elif step == 2:
            print("→ Frame wurde gesetzt. Warte eine Schleife ab, bevor Tracking startet...")
            state["step"] = 3
            return 0.5

        elif step == 3:
            _run_backward_track(ctx)
            state["step"] = 4
            return 0.5

        elif step == 4:
            res = _stability_tick(ctx, clip)
            if res == 'FINISHED':
                return None
            return 0.5

        return 0.5

    bpy.app.timers.register(_tick, first_interval=0.5)
    return {'RUNNING_MODAL'}
