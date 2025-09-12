from __future__ import annotations
# properties.py
import bpy
from bpy.props import StringProperty, IntProperty


class RepeatEntry(bpy.types.PropertyGroup):
    frame: StringProperty(name="Frame")
    count: IntProperty(name="Count")


def ensure_repeat_overlay_props():
    """Register Scene RNA properties; do NOT touch bpy.context during register."""
    if not hasattr(bpy.types.Scene, "kc_show_repeat_overlay"):
        bpy.types.Scene.kc_show_repeat_overlay = bpy.props.BoolProperty(
            name="Repeat-Overlay",
            description="Zeigt die Wiederholungs-Kurve über die Szenenlänge",
            default=False,
            update=lambda s, c: _toggle_repeat_overlay(s),
        )
    if not hasattr(bpy.types.Scene, "kc_repeat_overlay_height"):
        bpy.types.Scene.kc_repeat_overlay_height = bpy.props.IntProperty(
            name="Höhe (px)",
            description="Pixel-Höhe des Repeat-Overlays im Clip-Editor",
            default=120,
            min=40,
            soft_max=400,
            update=lambda s, c: _tag_redraw(),
        )
    # Kein Zugriff auf bpy.context.scene hier – ID-Properties werden lazy im Draw/Write angelegt.

def _toggle_repeat_overlay(scene):
    from ..ui.repeat_overlay import enable_repeat_overlay, disable_repeat_overlay
    if getattr(scene, "kc_show_repeat_overlay", False):
        enable_repeat_overlay()
    else:
        disable_repeat_overlay()
    _tag_redraw()

def _tag_redraw():
    try:
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'CLIP_EDITOR':
                    for r in a.regions:
                        if r.type == 'WINDOW':
                            r.tag_redraw()
    except Exception:
        # Während Register/Preferences kann bpy.context eingeschränkt sein.
        pass

def record_repeat_count(scene, frame, value):
    """Schreibt einen Repeat-Wert für einen absoluten Frame in die Serien-ID-Property."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return
    fs, fe = scene.frame_start, scene.frame_end
    n = max(0, int(fe - fs + 1))
    if n <= 0:
        return
    if scene.get("_kc_repeat_series") is None or len(scene["_kc_repeat_series"]) != n:
        scene["_kc_repeat_series"] = [0.0] * n
    idx = int(frame) - int(fs)
    if 0 <= idx < n:
        series = list(scene["_kc_repeat_series"])
        try:
            fval = float(value)
        except Exception:
            fval = 0.0
        series[idx] = float(max(0.0, fval))        scene["_kc_repeat_series"] = series
        _tag_redraw()
