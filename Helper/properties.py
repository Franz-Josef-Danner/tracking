"""Scene properties for Repeat Scope overlay."""

import bpy
from typing import Dict, List, Tuple, Any


# ---------------------------------------------------------------------------
# Szene-Properties werden exklusiv in ui/__init__.py registriert.
# Diese No-Op-Funktion bleibt erhalten, falls ältere Aufrufer sie noch callen.
# ---------------------------------------------------------------------------
def register_scene_properties() -> None:
    """No-op: Properties owned by ui.__init__.py."""
    pass


def unregister_scene_properties() -> None:
    """No-op: Properties are removed by ui.__init__.unregister()."""
    pass


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

