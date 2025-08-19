# SPDX-License-Identifier: GPL-2.0-or-later
"""
Blender Add-on Helper: Track vorwärts bis zum Szenenende (Invoke Default)

Funktionen:
- helper_track_forward_sequence_invoke_default():
    Nutzt den eingebauten Operator mit 'INVOKE_DEFAULT' und sequence=True
    (entspricht "Track Forwards" durch die gesamte Sequenz des Clips).

- helper_track_forward_to_scene_end_invoke_default():
    Startet einen eigenen modal Operator, der schrittweise (frameweise)
    tracking ausführt und exakt am Szenenende (scene.frame_end) stoppt.

Hinweise:
- Es muss ein CLIP_EDITOR geöffnet sein und im aktiven Space ein Movie Clip
  geladen sein. Außerdem sollten Marker/Tracks selektiert sein.
- Beide Varianten respektieren die aktuellen UI/Tracking-Einstellungen.
- Der Modal-Operator verwendet für den ersten Schritt 'INVOKE_DEFAULT' und
  anschließend 'EXEC_DEFAULT' für Einzel-Schritte, um exakt bis frame_end zu
  laufen.
"""

from __future__ import annotations

import bpy
from bpy.types import Operator


# ------------------------------------------------------------
# Context-Utilities
# ------------------------------------------------------------

def _find_clip_context() -> dict:
    """Sucht eine geeignete Override-Context-Map für bpy.ops.clip.*.

    Returns
    -------
    dict
        Kontext-Override mit window, screen, area, region, space_data.

    Raises
    ------
    RuntimeError
        Wenn kein CLIP_EDITOR mit WINDOW-Region gefunden wurde.
    """
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        space = area.spaces.active
                        return {
                            'window': window,
                            'screen': screen,
                            'area': area,
                            'region': region,
                            'space_data': space,
                        }
    raise RuntimeError("Kein CLIP_EDITOR mit WINDOW-Region im aktuellen UI-Layout gefunden.")


def _has_selected_markers(override: dict) -> tuple[bool, str | None]:
    """Prüft, ob im aktiven Clip selektierte Tracks/Marker vorhanden sind."""
    space = override.get('space_data')
    if not space or not getattr(space, 'clip', None):
        return False, "Im Clip-Editor ist kein Movie Clip aktiv."

    clip = space.clip
    tracking = clip.tracking

    # Mindestens ein Track selektiert?
    selected_tracks = [t for t in tracking.tracks if t.select]
    if not selected_tracks:
        return False, "Keine selektierten Tracks im aktiven Clip."

    return True, None


# ------------------------------------------------------------
# Öffentliche Helper-Funktionen
# ------------------------------------------------------------

def helper_track_forward() -> set:
    """Entspricht dem Standard-Tracking vorwärts über die Sequenz.

    Verwendet den eingebauten Operator mit 'INVOKE_DEFAULT' + sequence=True.
    Läuft bis zum Clip-Ende (nicht zwingend Szenenende!).
    """
    override = _find_clip_context()
    ok, msg = _has_selected_markers(override)
    if not ok:
        raise RuntimeError(msg)

    return bpy.ops.clip.track_markers(
        override,
        'INVOKE_DEFAULT',
        backwards=False,
        sequence=True,
    )


# ------------------------------------------------------------
# Modal-Operator: Exakt bis scene.frame_end
# ------------------------------------------------------------

class BW_OT_track_to_scene_end(Operator):
    """Trackt selektierte Marker vorwärts bis zum Szenenende.

    - Startet mit 'INVOKE_DEFAULT' (respektiert UI/Defaults)
    - Danach per Timer frameweise 'EXEC_DEFAULT' bis frame_end
    """

    bl_idname = "bw.track_to_scene_end"
    bl_label = "Track vorwärts bis Szenenende"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    _timer = None
    _target_frame: int | None = None

    def _step(self, context: bpy.types.Context) -> bool:
        """Führt einen Tracking-Einzelschritt aus und rückt 1 Frame vor.

        Returns
        -------
        bool
            True, wenn weitergemacht werden soll; False, wenn fertig/abbruch.
        """
        current = context.scene.frame_current
        assert self._target_frame is not None

        if current >= self._target_frame:
            return False

        override = _find_clip_context()
        try:
            # Einzel-Schritt nach vorn (ohne Sequenz)
            bpy.ops.clip.track_markers(
                override,
                'EXEC_DEFAULT',
                backwards=False,
                sequence=False,
            )
        except RuntimeError as ex:  # z.B. Poll-Error oder Tracking-Stop
            self.report({'WARNING'}, f"Tracking abgebrochen/fehlgeschlagen: {ex}")
            return False

        # Sicherstellen, dass wir im Zeitcursor vorankommen
        context.scene.frame_set(min(current + 1, self._target_frame))
        return True

    # ---- bpy.types.Operator API ----

    def invoke(self, context: bpy.types.Context, _event):
        try:
            override = _find_clip_context()
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}

        ok, msg = _has_selected_markers(override)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        self._target_frame = context.scene.frame_end

        # 1. Erster Schritt mit INVOKE_DEFAULT (respektiert UI/Defaults)
        try:
            bpy.ops.clip.track_markers(
                override,
                'INVOKE_DEFAULT',
                backwards=False,
                sequence=False,
            )
        except RuntimeError as ex:
            self.report({'ERROR'}, f"Konnte Tracking nicht starten: {ex}")
            return {'CANCELLED'}

        # 2. Timer für weitere Einzel-Schritte
        wm = context.window_manager
        # Kleines Intervall, damit es zügig läuft; 0.0 -> so schnell wie möglich
        self._timer = wm.event_timer_add(time_step=0.0, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event):
        if event.type == 'TIMER':
            cont = self._step(context)
            if not cont:
                self.cancel(context)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def cancel(self, context: bpy.types.Context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


# ------------------------------------------------------------
# Bequemer Helper für Add-on-Code
# ------------------------------------------------------------

def helper_track_forward_to_scene_end_invoke_default():
    """Bequemer Funktionsaufruf für Add-ons/Skripte.

    Startet den oben definierten Modal-Operator. Kann z.B. direkt an einen
    Button gebunden werden: operator("bw.track_to_scene_end").
    """
    bpy.ops.bw.track_to_scene_end('INVOKE_DEFAULT')


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(BW_OT_track_to_scene_end)


def unregister():
    bpy.utils.unregister_class(BW_OT_track_to_scene_end)


if __name__ == "__main__":
    register()
