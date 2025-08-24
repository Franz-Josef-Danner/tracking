# Helper/bidirectional_track.py
# Zweck: Selektierte Tracking-Marker frameweise NUR VORWÄRTS tracken,
#        in einer Schleife, bis kein Track mehr Fortschritt macht.
#
# Drop‑in kompatibel zum Orchestrator in tracking_coordinator.py:
#  - Registriert einen Operator unter der ID "clip.bidirectional_track",
#    weil der Coordinator genau diesen aufruft (INVOKE_DEFAULT).
#  - Nutzt die Scene-Keys "bidi_active" und "bidi_result" zur Kommunikation.
#  - Akzeptiert (und ignoriert intern) die Properties
#      use_cooperative_triplets, auto_enable_from_selection
#    damit der Operator-Aufruf mit diesen Parametern nicht fehlschlägt.
#
# Zusätzlich wird ein Hilfsoperator "helper.track_selected_forward_until_done"
# bereitgestellt, falls du ihn separat aufrufen willst (F3-Suche etc.).
#
# Voraussetzungen:
#  - Ein CLIP_EDITOR muss geöffnet sein und einen Movie Clip anzeigen.
#  - Marker/Tracks müssen selektiert sein.
#
# PEP 8, defensive Fehlerbehandlung, keine Hintergrund-Threads.

from __future__ import annotations

import bpy
from typing import Iterable, Optional, Tuple, Any

# Scene-Schlüssel müssen zu tracking_coordinator.py passen
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"


# -----------------------------------------------------------------------------
# Kontext-/Utility-Funktionen
# -----------------------------------------------------------------------------

def _find_clip_context() -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """Suche einen CLIP_EDITOR nebst WINDOW-Region und SpaceClip.

    Returns:
        (area, region, space) oder (None, None, None)
    """
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if getattr(space, "type", None) == 'CLIP_EDITOR' and region is not None:
                return area, region, space
    return None, None, None


def _get_active_clip(space: Optional[Any]) -> Optional[Any]:
    """Gibt das aktive MovieClip des SpaceClip zurück, oder erstes verfügbares."""
    if space and getattr(space, "clip", None):
        return space.clip
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _selected_tracks(clip: Any) -> Iterable[Any]:
    if not clip:
        return []
    tracks = clip.tracking.tracks
    return [t for t in tracks if t.select and not t.mute and not t.disabled]


def _has_marker_at(track: Any, frame: int) -> bool:
    try:
        return track.markers.find_frame(frame) is not None
    except Exception:
        return any(m.frame == frame for m in track.markers)


def _can_attempt_step(track: Any, clip: Any, current_frame: int) -> bool:
    if track.mute or track.disabled:
        return False
    if not _has_marker_at(track, current_frame):
        return False
    next_frame = current_frame + 1
    end_frame = getattr(clip, "frame_end", None)
    if end_frame is not None and next_frame > int(end_frame):
        return False
    return True


# -----------------------------------------------------------------------------
# Kernfunktion: frameweise vorwärts tracken, bis Ende
# -----------------------------------------------------------------------------

def track_selected_forward_until_done() -> int:
    """Trackt selektierte Marker frameweise VORWÄRTS, bis kein Fortschritt mehr möglich ist.

    Returns:
        Anzahl der tatsächlich durchgeführten Vorwärts-Schritte (Frames).
    Raises:
        RuntimeError: wenn kein CLIP_EDITOR/Clip vorhanden ist.
    """
    area, region, space = _find_clip_context()
    if not all((area, region, space)):
        raise RuntimeError(
            "Kein CLIP_EDITOR mit gültiger WINDOW-Region gefunden. "
            "Bitte öffne einen Movie Clip im Movie Clip Editor."
        )

    clip = _get_active_clip(space)
    if not clip:
        raise RuntimeError("Kein aktives Movie Clip gefunden.")

    scene = bpy.context.scene
    step_count = 0

    while True:
        current_frame = int(scene.frame_current)
        next_frame = current_frame + 1

        tracks = list(_selected_tracks(clip))
        if not tracks:
            break

        if not any(_can_attempt_step(t, clip, current_frame) for t in tracks):
            break

        # Merken, welche Tracks bereits Marker im next_frame hatten
        had_next = {t.name: _has_marker_at(t, next_frame) for t in tracks}

        # Exakt EIN Frame tracken
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.track_markers(backwards=False, sequence=False)

        # Fortschritt prüfen
        progressed = False
        for t in tracks:
            now_has = _has_marker_at(t, next_frame)
            if now_has and not had_next.get(t.name, False):
                progressed = True

        if not progressed:
            break

        scene.frame_set(next_frame)
        step_count += 1

    return step_count


# -----------------------------------------------------------------------------
# UI-Operator: helper.track_selected_forward_until_done (direkter Aufruf)
# -----------------------------------------------------------------------------

class HELPER_OT_track_selected_forward_until_done(bpy.types.Operator):
    bl_idname = "helper.track_selected_forward_until_done"
    bl_label = "Track: Selektierte vorwärts (bis fertig)"
    bl_options = {'REGISTER', 'UNDO'}

    performed_steps: bpy.props.IntProperty(name="Durchgeführte Schritte", default=0, options={'HIDDEN'})

    def execute(self, context):
        try:
            steps = track_selected_forward_until_done()
        except RuntimeError as err:
            self.report({'ERROR'}, str(err))
            return {'CANCELLED'}
        self.performed_steps = int(steps)
        self.report({'INFO'}, f"Tracking beendet. Schritte: {steps}")
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Drop‑in Operator für den Coordinator: clip.bidirectional_track
# -----------------------------------------------------------------------------

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Kompatibler Operator für tracking_coordinator._state_track().

    Hinweis: Der Coordinator ruft diesen Operator mit INVOKE_DEFAULT und
    übergibt u. a. use_cooperative_triplets / auto_enable_from_selection.
    Wir akzeptieren diese Properties, nutzen sie hier aber nicht.
    """

    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (stepwise forward)"
    bl_options = {'REGISTER', 'UNDO'}

    # Erwartete (optionale) Properties aus dem Coordinator-Aufruf
    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Use Cooperative Triplets",
        default=True,
        description="Kompatibilitäts-Property – wird hier nicht verwendet.",
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Auto Enable from Selection",
        default=True,
        description="Kompatibilitäts-Property – wird hier nicht verwendet.",
    )

    # Interner Status
    _running: bool = False

    @classmethod
    def poll(cls, context):
        # Nur im CLIP_EDITOR sinnvoll; spiegelt Coordinator.poll()
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    def invoke(self, context, event):  # noqa: D401
        scn = context.scene
        # Falls bereits aktiv, sofort freundlich abbrechen (idempotent)
        if scn.get(_BIDI_ACTIVE_KEY, False):
            self.report({'INFO'}, "Bidirectional-Track läuft bereits – überspringe zweiten Start.")
            return {'CANCELLED'}

        # Startsignal setzen
        scn[_BIDI_ACTIVE_KEY] = True
        scn[_BIDI_RESULT_KEY] = ""
        self._running = True

        # In diesem Fall blockierend ausführen (kein eigener Modal-Loop nötig)
        return self.execute(context)

    def execute(self, context):
        scn = context.scene
        try:
            steps = track_selected_forward_until_done()
            # Ergebnis kommunizieren
            scn[_BIDI_RESULT_KEY] = "FINISHED"
            self.report({'INFO'}, f"Bidirectional-Track fertig. Schritte: {steps}")
            return {'FINISHED'}
        except RuntimeError as err:
            scn[_BIDI_RESULT_KEY] = "FAILED"
            self.report({'ERROR'}, str(err))
            return {'CANCELLED'}
        finally:
            scn[_BIDI_ACTIVE_KEY] = False
            self._running = False


# -----------------------------------------------------------------------------
# Register / Unregister
# -----------------------------------------------------------------------------

classes = (
    HELPER_OT_track_selected_forward_until_done,
    CLIP_OT_bidirectional_track,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
