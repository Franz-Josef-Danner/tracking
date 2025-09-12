"""Scene properties for Repeat Scope overlay."""

import bpy
from bpy.props import BoolProperty, IntProperty
from importlib import import_module


# ---- Update-Callback: toggle handler lazily to avoid import cycles ----
def _kc_update_repeat_scope(self, context):
    try:
        base = __package__.split('.')[0]  # e.g. "tracking"
        mod = import_module(f"{base}.ui.repeat_scope")
        mod.enable_repeat_scope(bool(getattr(self, "kc_show_repeat_scope", False)))
    except Exception as e:
        print("[RepeatScope] update skipped:", e)


def register():
    sc = bpy.types.Scene
    sc.kc_show_repeat_scope = BoolProperty(
        name="Repeat-Scope anzeigen",
        description="Overlay für Repeat-Scope ein-/ausschalten",
        default=False,
        update=_kc_update_repeat_scope,
    )
    sc.kc_repeat_scope_height = IntProperty(
        name="Höhe",
        description="Höhe des Repeat-Scope im Viewport",
        default=140,
        min=80,
        max=600,
    )
    sc.kc_repeat_scope_bottom = BoolProperty(
        name="Unten andocken",
        description="Overlay am unteren Rand andocken",
        default=True,
    )
    sc.kc_repeat_scope_margin_x = IntProperty(
        name="Rand X",
        description="Horizontaler Innenabstand",
        default=12,
        min=0,
        max=400,
    )
    sc.kc_repeat_scope_show_cursor = BoolProperty(
        name="Cursorlinie",
        description="Aktuellen Frame als Linie anzeigen",
        default=True,
    )


def unregister():
    sc = bpy.types.Scene
    for attr in (
        "kc_show_repeat_scope",
        "kc_repeat_scope_height",
        "kc_repeat_scope_bottom",
        "kc_repeat_scope_margin_x",
        "kc_repeat_scope_show_cursor",
    ):
        if hasattr(sc, attr):
            delattr(sc, attr)


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
    """Store a repeat value for an absolute frame in a scene property."""
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

