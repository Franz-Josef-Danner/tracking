# SPDX-License-Identifier: MIT
"""
Refine High Error (modal, mit sichtbarem Frame-Redraw)

Dieses Modul führt die bisher "im Hintergrund" laufende High-Error-Refine-Logik
timer-gesteuert als Modal-Operator aus. Pro Timer-Takt wird GENAU EIN Frame
verarbeitet, wodurch der Framewechsel im UI sichtbar ist.

Flags an der Scene (analog zu Bidi):
    scene["refine_active"] : bool
    scene["refine_result"] : str ("", "OK", "CANCELLED", "ERROR:<msg>")

Start via:
    bpy.ops.kaiserlich.refine_high_error('INVOKE_DEFAULT',
        start_frame=sf, end_frame=ef, step=1, threshold=2.0)

oder aus Python:
    from .refine_high_error import run_refine_modal
    run_refine_modal(context, start=sf, end=ef, step=1, threshold=2.0)
"""

from __future__ import annotations

import bpy
from bpy.types import Operator, Context, Area, Region
from typing import List, Optional


# -----------------------------------------------------------------------------
# Utility
# -----------------------------------------------------------------------------

def _find_clip_area_and_region(context: Context) -> tuple[Optional[Area], Optional[Region]]:
    """Finde eine CLIP_EDITOR Area/Region für sichere Operator-Contexts."""
    win = getattr(context, "window", None)
    if not win:
        return None, None
    screen = win.screen
    if not screen:
        return None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
            return area, None
    return None, None


def _tag_redraw_all(context: Context) -> None:
    """Sichtbares UI-Feedback in relevanten Areas."""
    wm = context.window_manager
    for win in wm.windows:
        scr = win.screen
        for area in scr.areas:
            if area.type in {'CLIP_EDITOR', 'IMAGE_EDITOR', 'PROPERTIES', 'GRAPH_EDITOR'}:
                area.tag_redraw()


# -----------------------------------------------------------------------------
# Pro-Frame Arbeit
# -----------------------------------------------------------------------------

def _refine_step(context: Context, *, threshold: float) -> None:
    """
    Führt die High-Error-Verbesserung genau für den AKTUELLEN Frame aus.

    Die hier implementierte Standard-Variante nutzt die Blender-Operatoren
    für Tracking-Cleanup. Passe diesen Block bei Bedarf an deine bisherige
    Refine-Logik an (Marker-Selektionsregeln, eigene Filter etc.).

    Strategie:
      1) Reprojektion-Fehler über clip.clean_tracks (error=threshold) bereinigen.
      2) Optional: Kürzeste Tracks entfernen (frames=0 belässt alles; erhöhe, falls gewünscht).
    """
    clip = context.edit_movieclip
    if clip is None:
        return

    area, region = _find_clip_area_and_region(context)

    # Sicherer Context für clip-Operatoren
    if area and region:
        with context.temp_override(area=area, region=region):
            try:
                # Reprojection-Fehler bereinigen (nur aktueller Frame wird angezeigt; Operator wirkt global)
                bpy.ops.clip.clean_tracks(frames=0, error=threshold, action='SELECT')
                # Hinweis: Wenn du statt SELECT direkt löschen willst:
                # bpy.ops.clip.clean_tracks(frames=0, error=threshold, action='DELETE_TRACKS')
            except Exception as ex:
                print(f"[Refine] clean_tracks failed: {ex}")
    else:
        # Fallback ohne speziellen UI-Kontext
        try:
            bpy.ops.clip.clean_tracks(frames=0, error=threshold, action='SELECT')
        except Exception as ex:
            print(f"[Refine] clean_tracks failed (no UI override): {ex}")


# -----------------------------------------------------------------------------
# Modal Operator
# -----------------------------------------------------------------------------

class KAISERLICH_OT_refine_high_error(Operator):
    """Refine High Error (Live) – verarbeitet eine Frame-Range sichtbar im UI."""
    bl_idname = "kaiserlich.refine_high_error"
    bl_label = "Refine High Error (Live)"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    start_frame: bpy.props.IntProperty(name="Start", default=1, min=1)
    end_frame: bpy.props.IntProperty(name="End", default=250, min=1)
    step: bpy.props.IntProperty(name="Step", default=1, min=1)
    threshold: bpy.props.FloatProperty(
        name="Error Threshold (px)", default=2.0, min=0.1, soft_max=10.0
    )

    _timer: Optional[object] = None
    _frames: List[int] = []
    _area: Optional[Area] = None
    _region: Optional[Region] = None

    # --- Lifecycle ---------------------------------------------------------
    def invoke(self, context: Context, event):
        scn = context.scene

        # Konflikt vermeiden: nicht starten, wenn Bidi aktiv ist
        if scn.get("bidi_active", False):
            self.report({'WARNING'}, "Bidirectional Tracking läuft – Refine später starten.")
            return {'CANCELLED'}

        # Frames vorbereiten
        start = min(self.start_frame, self.end_frame)
        end = max(self.start_frame, self.end_frame)
        self._frames = list(range(start, end + 1, max(1, self.step)))

        # Clip-Editor Area/Region merken (für Override)
        self._area, self._region = _find_clip_area_and_region(context)

        # Flags setzen (analog zu Bidi)
        scn["refine_active"] = True
        scn["refine_result"] = ""

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=getattr(context, "window", None))
        wm.modal_handler_add(self)

        self.report({'INFO'}, f"Refine gestartet: {start}–{end} (step {self.step})")
        return {'RUNNING_MODAL'}

    def modal(self, context: Context, event):
        if event.type == 'TIMER':
            try:
                if not self._frames:
                    return self._finish(context, result="OK")

                frame = self._frames.pop(0)

                # UI-sichtbarer Framewechsel
                context.scene.frame_set(frame)
                _tag_redraw_all(context)

                # Pro-Frame Arbeit
                _refine_step(context, threshold=self.threshold)

                return {'RUNNING_MODAL'}

            except Exception as ex:
                return self._finish(context, result=f"ERROR:{ex}")

        elif event.type in {'ESC'}:
            return self._finish(context, result="CANCELLED")

        return {'RUNNING_MODAL'}

    # --- Helpers -----------------------------------------------------------
    def _finish(self, context: Context, result: str):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        scn = context.scene
        scn["refine_active"] = False
        scn["refine_result"] = result

        _tag_redraw_all(context)
        self.report({'INFO'}, f"Refine beendet: {result}")
        return {'FINISHED'} if result == "OK" else {'CANCELLED'}


# -----------------------------------------------------------------------------
# Public Convenience API
# -----------------------------------------------------------------------------

def run_refine_modal(context: Context, start: int, end: int, step: int = 1, threshold: float = 2.0):
    """Bequemer Python-Einstieg."""
    return bpy.ops.kaiserlich.refine_high_error(
        'INVOKE_DEFAULT',
        start_frame=start, end_frame=end, step=step, threshold=threshold
    )


# -----------------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------------

_classes = (
    KAISERLICH_OT_refine_high_error,
)

def register():
    from bpy.utils import register_class
    for cls in _classes:
        register_class(cls)

def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(_classes):
        unregister_class(cls)
