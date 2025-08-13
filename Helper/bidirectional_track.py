# Helper/bidirectional_track.py
import bpy

from .solve_camera import solve_watch_clean

__all__ = ("run_bidirectional_track",)

def _clip_override(context):
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None


def run_bidirectional_track(context):
    """
    Reiner Helper, der die frühere modal-Operator-Logik 1:1 via bpy.app.timers ausführt.
    Steps:
      0) Vorwärts-Tracking starten
      1) Frame auf Start zurücksetzen
      2) eine Schleife warten
      3) Rückwärts-Tracking starten
      4) Stabilitätsprüfung; bei Stabilität: kurze Tracks bereinigen und Low-Marker starten
    Rückgabe: {'RUNNING_MODAL'} (Timer aktiv) oder {'FINISHED'}/{'CANCELLED'} synchron,
    je nach sofortigem Zustand. In der Regel startet der Timer und gibt {'RUNNING_MODAL'} zurück.
    """
    state = {
        "step": 0,
        "stable_count": 0,
        "prev_marker_count": -1,
        "prev_frame": -1,
        "start_frame": int(getattr(context.scene, "frame_current", 1)),
        "active": True,
    }

    print("[Tracking] Schritt: 0")

    def _cleanup():
        state["active"] = False  # Timer beenden, indem Callback None zurückgibt

    def _get_clip_from_space(ctx):
        space = getattr(ctx, "space_data", None)
        return getattr(space, "clip", None) if space else None

    def _ensure_active_clip(ctx):
        """
        Sichert, dass im aktiven CLIP_EDITOR ein Clip gesetzt ist.
        Fallback: erster MovieClip aus bpy.data.movieclips.
        Gibt den Clip zurück oder None, wenn keiner existiert.
        """
        clip = _get_clip_from_space(ctx)
        if clip:
            return clip

        # Fallback: irgendeinen verfügbaren Clip nehmen
        try:
            fallback_clip = next(iter(bpy.data.movieclips))
        except StopIteration:
            print("Kein MovieClip in der Datei vorhanden.")
            return None

        # Falls wir einen CLIP_EDITOR-Kontext übersteuern können, Clip dort setzen
        ov = _clip_override(ctx)
        if ov:
            try:
                with ctx.temp_override(**ov):
                    ov['space_data'].clip = fallback_clip
                print(f"[Tracking] Fallback-Clip gesetzt: {fallback_clip.name}")
            except Exception as e:
                print(f"[Tracking] Konnte Fallback-Clip nicht im UI setzen: {e}")

        # Auch ohne gesetzten UI-Clip können wir mit dem Datablock weiterarbeiten
        return fallback_clip

    def _run_forward_track():
        print("→ Starte Vorwärts-Tracking...")
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)

    def _reset_to_start_frame(ctx):
        print("→ Warte auf Abschluss des Vorwärts-Trackings...")
        ctx.scene.frame_current = state["start_frame"]
        print(f"← Frame zurückgesetzt auf {state['start_frame']}")

    def _run_backward_track():
        print("→ Starte Rückwärts-Tracking...")
        bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)

    def _stability_tick(ctx):
        clip = _ensure_active_clip(ctx)
        if clip is None:
            _cleanup()
            return {'CANCELLED'}

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

        if state["stable_count"] >= 2:
            print("✓ Tracking stabil erkannt – bereinige kurze Tracks.")
            try:
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
            except Exception as e:
                print(f"[Tracking] clean_short_tracks fehlgeschlagen: {e}")

            # Low-Marker-Operator sauber starten (kein Feedback, kein Flag)
            ov = _clip_override(ctx)
            try:
                if ov:
                    with ctx.temp_override(**ov):
                        bpy.ops.clip.find_low_marker_frame('INVOKE_DEFAULT', use_scene_basis=True)
                else:
                    bpy.ops.clip.find_low_marker_frame('INVOKE_DEFAULT', use_scene_basis=True)
            except Exception as e:
                print(f"[Tracking] Low-Marker-Operator konnte nicht gestartet werden: {e}")

            _cleanup()
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    # Timer-Callback: bildet die frühere modal()-State-Maschine ab
    def _tick():
        if not state["active"]:
            return None  # Timer stoppen

        ctx = bpy.context
        clip = _ensure_active_clip(ctx)
        if clip is None:
            print("Kein aktiver Clip im Tracking-Editor gefunden (und kein Fallback verfügbar).")
            _cleanup()
            return None  # -> beendet

        step = state["step"]

        if step == 0:
            _run_forward_track()
            state["step"] = 1
            return 0.5

        elif step == 1:
            _reset_to_start_frame(ctx)
            state["step"] = 2
            return 0.5

        elif step == 2:
            print("→ Frame wurde gesetzt. Warte eine Schleife ab, bevor Tracking startet...")
            state["step"] = 3
            return 0.5

        elif step == 3:
            _run_backward_track()
            state["step"] = 4
            return 0.5

        elif step == 4:
            res = _stability_tick(ctx)
            if isinstance(res, dict) and 'FINISHED' in res:
                return None  # fertig -> Timer stoppen
            if isinstance(res, dict) and 'CANCELLED' in res:
                return None
            return 0.5

        # Fallback
        return 0.5

    # Timer starten
    bpy.app.timers.register(_tick, first_interval=0.5)

    # Verhalten analog zum ursprünglichen Operator-Start: läuft modal
    return {'RUNNING_MODAL'}
