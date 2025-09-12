import bpy
from importlib import import_module

def _toggle_repeat_scope(self, context):
    """
    UI-Update-Callback für Scene.kc_show_repeat_scope.
    Bindet den Overlay-Handler sicher an/ab.
    """
    try:
        # Basis-Paket ermitteln (z.B. 'tracking' aus 'tracking.Helper')
        base = __package__.split('.')[0] if __package__ else None
        mod = import_module(f"{base}.ui.repeat_scope") if base else import_module("ui.repeat_scope")
        if hasattr(mod, "enable_repeat_scope"):
            mod.enable_repeat_scope(bool(getattr(context.scene, "kc_show_repeat_scope", False)))
    except Exception as e:
        print("[RepeatScope] toggle failed:", e)

def ensure_repeat_scope_props():
    s = bpy.types.Scene
    if not hasattr(s, "kc_show_repeat_scope"):
        s.kc_show_repeat_scope = bpy.props.BoolProperty(
            name="Repeat-Scope anzeigen",
            default=False,
            update=_toggle_repeat_scope,
            description="Zeigt das Repeat-Scope-Overlay im Movie Clip Editor an."
        )
    if not hasattr(s, "kc_overlay_height"):
        s.kc_overlay_height = bpy.props.IntProperty(name="Höhe (px)", default=140, min=60, max=800)
    if not hasattr(s, "kc_overlay_margin_bottom"):
        s.kc_overlay_margin_bottom = bpy.props.IntProperty(name="Abstand unten (px)", default=24, min=0, max=200)
    if not hasattr(s, "kc_overlay_margin_side"):
        s.kc_overlay_margin_side = bpy.props.IntProperty(name="Seitenrand (px)", default=12, min=0, max=200)
    if not hasattr(s, "kc_overlay_show_cursor"):
        s.kc_overlay_show_cursor = bpy.props.BoolProperty(name="Frame-Cursor", default=True)

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
        series[idx] = float(max(0.0, fval))
        scene["_kc_repeat_series"] = series
        _tag_redraw()
