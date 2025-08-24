# Helper/bidirectional_track.py
# Zweck: Selektierte Tracking-Marker frameweise NUR VORWÄRTS tracken,
#        in einer Schleife, bis kein Track mehr Fortschritt macht.
#
# Drop-in kompatibel zum Orchestrator in tracking_coordinator.py:
#  - Operator-ID: "clip.bidirectional_track" (so ruft ihn der Coordinator auf)
#  - Szene-Keys:  "bidi_active" und "bidi_result" für den Status-Handshake
#  - akzeptiert die Properties: use_cooperative_triplets, auto_enable_from_selection
#
# Zusätzlich: Utility-Operator "helper.track_selected_forward_until_done" für manuelle Nutzung.

from __future__ import annotations

import bpy
from typing import Iterable, Optional, Tuple, Any

# Scene keys (müssen mit tracking_coordinator.py übereinstimmen)
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"


# -----------------------------------------------------------------------------
# Kontext-/Utility-Funktionen
# -----------------------------------------------------------------------------

def _find_clip_context() -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """Suche einen CLIP_EDITOR nebst WINDOW-Region und SpaceClip."""
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
    """Nur nach Track-Selektion filtern (Blender 4.x: keine .mute/.disabled-Garantie)."""
    if not clip:
        return []
    tracks = clip.tracking.tracks
    return [t for t in tracks if bool(getattr(t, "select", False))]


def _has_marker_at(track: Any, frame: int) -> bool:
    """Prüfen, ob Track einen Marker an 'frame' hat (API-kompatibel)."""
    try:
        return track.markers.find_frame(frame) is not None
    except Exception:
        return any(getattr(m, "frame", None) == frame for m in track.markers)


def _can_attempt_step(track: Any, clip: Any, current_frame: int) -> bool:
    """Darf/soll dieser Track einen Vorwärts-Schritt versuchen?"""
    # defensiv gegen Build-Unterschiede
    if bool(getattr(track, "mute", False)) or bool(getattr(track, "muted", False)):
        return False
    if bool(getattr(track, "disabled", False)) or bool(getattr(track, "hide", False)):
        return False
    if not _has_marker_at(track, current_frame):
        return False
    # Clipgrenze beachten
    next_frame = current_frame + 1
    end_frame = getattr(clip, "frame_end", None)
    try:
        if end_frame is not None and next_frame > int(end_frame):
            return False
    except Exception:
        pass
    return True


# -----------------------------------------------------------------------------
# Kernfunktion: frameweise vorwärts tracken, bis Ende
# -----------------------------------------------------------------------------

def track_selected_forward_until_done() -> int:
    """Trackt selektierte Marker frameweise VORWÄRTS, bis kein Fortschritt mehr möglich ist.

    Returns:
        int: Anzahl der tatsächlich durchgeführten Vorwärts-Schritte (Frames).
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

        # Selektion erfassen
        all_tracks = list(clip.tracking.tracks)
        selected_tracks = [t for t in all_tracks if bool(getattr(t, "select", False))]
        if not selected_tracks:
            break

        # Kandidaten bestimmen (Marker am current_frame vorhanden etc.)
        candidates = [t for t in selected_tracks if _can_attempt_step(t, clip, current_frame)]
        if not candidates:
            break

        # Nur Tracks tracken, die im next_frame noch keinen Marker besitzen
        eligible = [t for t in candidates if not _has_marker_at(t, next_frame)]
        if not eligible:
            break  # nichts zu tun

        # Selektion temporär auf eligible einschränken
        original_sel = {t.name: bool(getattr(t, "select", False)) for t in all_tracks}
        try:
            for t in all_tracks:
                try:
                    t.select = False
                except Exception:
                    pass
            for t in eligible:
                try:
                    t.select = True
                except Exception:
                    pass

            # Marker am aktuellen Frame markieren (Operator ist markerbasiert)
            for t in eligible:
                try:
                    mk = t.markers.find_frame(current_frame)
                    if mk is not None:
                        mk.select = True
                except Exception:
                    pass

            # Genau EIN Frame tracken
            with bpy.context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
        finally:
            # ursprüngliche Track-Selektion wiederherstellen
            for t in all_tracks:
                try:
                    t.select = bool(original_sel.get(t.name, False))
                except Exception:
                    pass

        # Fortschritt prüfen
        progressed = any(_has_marker_at(t, next_frame) for t in eligible)
        if not progressed:
            break

        # Einen Frame weiter
        scene.frame_set(next_frame)
        step_count += 1

    return step_count


# -----------------------------------------------------------------------------
# UI-Operator: helper.track_selected_forward_until_done (manuell via F3)
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
# Drop-in Operator für den Coordinator: clip.bidirectional_track
# -----------------------------------------------------------------------------

class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Kompatibler Operator für tracking_coordinator._state_track()."""

    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (stepwise forward)"
    bl_options = {'REGISTER', 'UNDO'}

    # Erwartete (optionale) Properties aus dem Coordinator-Aufruf:
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

    _running: bool = False  # interner Status

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    def invoke(self, context, event):
        scn = context.scene
        # idempotent: nicht doppelt starten
        if scn.get(_BIDI_ACTIVE_KEY, False):
            self.report({'INFO'}, "Bidirectional-Track läuft bereits – überspringe zweiten Start.")
            return {'CANCELLED'}

        scn[_BIDI_ACTIVE_KEY] = True
        scn[_BIDI_RESULT_KEY] = ""
        self._running = True
        # blockierend ausführen (kein eigener Modal-Loop)
        return self.execute(context)

    def execute(self, context):
        scn = context.scene
        try:
            steps = int(track_selected_forward_until_done())
            if steps > 0:
                scn[_BIDI_RESULT_KEY] = "FINISHED"
                self.report({'INFO'}, f"Bidirectional-Track fertig. Schritte: {steps}")
            else:
                scn[_BIDI_RESULT_KEY] = "NOOP"
                self.report({'INFO'}, "Bidirectional-Track: nichts zu tun (0 Schritte)")
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
