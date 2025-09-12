from __future__ import annotations
# properties.py
import bpy
from bpy.props import StringProperty, IntProperty

class RepeatEntry(bpy.types.PropertyGroup):
    frame: StringProperty(name="Frame")
    count: IntProperty(name="Count")

def ensure_repeat_overlay_props():
    scn = bpy.context.scene
    if scn is None:
        return
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
            default=120, min=40, soft_max=400,
            update=lambda s, c: _tag_redraw(),
        )
    if scn.get("_kc_repeat_series") is None:
        scn["_kc_repeat_series"] = []
    _tag_redraw()

def _toggle_repeat_overlay(scene: bpy.types.Scene):
    from ..ui.repeat_overlay import enable_repeat_overlay, disable_repeat_overlay
    if getattr(scene, "kc_show_repeat_overlay", False):
        enable_repeat_overlay()
    else:
        disable_repeat_overlay()
    _tag_redraw()

def _tag_redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        r.tag_redraw()

def record_repeat_count(scene: bpy.types.Scene, frame: int, value: float):
    if scene is None:
        scene = bpy.context.scene
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
        series[idx] = float(max(0.0, value))
        scene["_kc_repeat_series"] = series
        _tag_redraw()
