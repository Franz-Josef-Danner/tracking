"""Scene properties + helpers for the Repeat Scope overlay."""

import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty
from importlib import import_module

__all__ = ("register", "unregister", "record_repeat_count")


# -----------------------------------------------------------------------------
# Update-Callback: Toggle Handler (lazy import, robust bei Bindestrichen)
# -----------------------------------------------------------------------------
def _kc_update_repeat_scope(self, context):
    try:
        # Relativ importieren, damit ein Addon-Ordnername mit "-" nicht stört.
        mod = import_module("..ui.repeat_scope", __package__)
        enable = bool(getattr(self, "kc_show_repeat_scope", False))
        mod.enable_repeat_scope(enable)
    except Exception as e:
        # Beim Laden/Prefs nicht hart fehlschlagen.
        print("[RepeatScope] update skipped:", e)


def register():
    """Register Repeat-Scope Scene properties (von Addon-__init__.py aufgerufen)."""
    Scene = bpy.types.Scene

    # Sichtbarkeit / Lifecycle (mit Update-Callback)
    Scene.kc_show_repeat_scope = BoolProperty(
        name="Repeat-Scope anzeigen",
        description="Overlay für Repeat-Scope ein-/ausschalten",
        default=False,
        update=_kc_update_repeat_scope,
    )

    # Layout
    Scene.kc_repeat_scope_height = IntProperty(
        name="Höhe",
        description="Höhe des Repeat-Scope (Pixel)",
        default=140, min=40, max=800,
    )
    Scene.kc_repeat_scope_bottom = IntProperty(
        name="Abstand unten",
        description="Abstand vom unteren Rand (Pixel)",
        default=24, min=0, max=2000,
    )
    Scene.kc_repeat_scope_margin_x = IntProperty(
        name="Rand X",
        description="Horizontaler Innenabstand (Pixel)",
        default=12, min=0, max=2000,
    )
    Scene.kc_repeat_scope_show_cursor = BoolProperty(
        name="Cursorlinie",
        description="Aktuellen Frame als Linie anzeigen",
        default=True,
    )
    Scene.kc_repeat_scope_levels = IntProperty(
        name="Höhenstufen",
        description="Anzahl der diskreten Höhenstufen für das Repeat-Scope (Quantisierung der Kurve)",
        default=36, min=2, max=200,
    )


def unregister():
    """Unregister Repeat-Scope Scene properties."""
    Scene = bpy.types.Scene
    for attr in (
        "kc_show_repeat_scope",
        "kc_repeat_scope_height",
        "kc_repeat_scope_bottom",
        "kc_repeat_scope_margin_x",
        "kc_repeat_scope_show_cursor",
        "kc_repeat_scope_levels",
    ):
        if hasattr(Scene, attr):
            delattr(Scene, attr)


# -----------------------------------------------------------------------------
# Helper: Serie für Repeats (wird von jump_to_frame.py befüllt)
# -----------------------------------------------------------------------------
def _tag_redraw() -> None:
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


def record_repeat_count(scene, frame, value) -> None:
    """Speichert den Repeat-Wert für einen absoluten Frame in Scene-ID-Props.

    Die Serie liegt in scene['_kc_repeat_series'] (Float-Liste in Frame-Range).
    Das Overlay liest diese Serie direkt und zeichnet sie.
    """
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

