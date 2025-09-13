"""Scene properties + helpers for the Repeat Scope overlay."""

import bpy
from bpy.props import BoolProperty, IntProperty
from importlib import import_module

__all__ = (
    "register",
    "unregister",
    "record_repeat_count",
    "record_repeat_series",
    "record_repeat_series_bulk",
    "record_repeat_bulk_map",
    "get_repeat_series_map",
    "ensure_repeat_scope_props",
)


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
    # Sichtbarer Radius-Parameter fürs Overlay-Fading (wenn nicht schon vorhanden)
    if not hasattr(Scene, "kc_repeat_scope_radius"):
        Scene.kc_repeat_scope_radius = IntProperty(
            name="Repeat-Fade-Radius",
            description="Ausbreitung der Wiederholungswerte in Frames f\u00fcr das Overlay",
            default=20, min=0, soft_max=200,
        )
    if not hasattr(Scene, "kc_repeat_fade_step"):
        Scene.kc_repeat_fade_step = IntProperty(
            name="Fade-Schritt (Frames)",
            description="Alle N Frames -1",
            default=5, min=1, soft_max=20,
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
        "kc_repeat_scope_radius",
        "kc_repeat_scope_levels",
        "kc_repeat_fade_step",
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
        # Nur anheben (kein versehentliches Absenken bereits geschriebener Hügel)
        existing = float(series[idx]) if idx < len(series) else 0.0
        series[idx] = max(existing, float(max(0.0, fval)))
        scene["_kc_repeat_series"] = series
        _tag_redraw()


def record_repeat_series(scene, series, *, mode: str = "set") -> None:
    """Schreibt eine komplette Serie in scene['_kc_repeat_series'] (legacy List-API)."""
    print("[RepeatScope] record_repeat_series: legacy list API")
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return
    fs = int(getattr(scene, "frame_start", 1))
    fe = int(getattr(scene, "frame_end", fs))
    mapping = {}
    for i, v in enumerate(series or []):
        try:
            iv = int(v)
        except Exception:
            continue
        f = fs + i
        if fs <= f <= fe:
            mapping[f] = iv
    if mode == "max":
        base = get_repeat_series_map(scene)
        out = dict(base)
        for f, v in mapping.items():
            if v > out.get(f, 0):
                out[f] = v
    else:
        out = mapping
    out = {int(f): int(v) for f, v in out.items() if fs <= int(f) <= fe}
    scene["_kc_repeat_series"] = out
    try:
        _tag_redraw()
    except Exception:
        pass

def record_repeat_series_bulk(scene, mapping: dict[int, int]) -> None:
    """Atomarer Bulk-Write der Repeat-Serie mit monotoner Erh\u00f6hung."""
    try:
        current = scene.get("_kc_repeat_series")
        base = dict(current) if isinstance(current, dict) else {}
        out = dict(base)
        for f, v in mapping.items():
            try:
                fv = int(v)
            except Exception:
                continue
            prev = int(out.get(f, 0))
            if fv > prev:
                out[f] = fv
        fs, fe = int(scene.frame_start), int(scene.frame_end)
        out = {int(f): int(v) for f, v in out.items() if fs <= int(f) <= fe}
        scene["_kc_repeat_series"] = out
    except Exception:
        # Fallback: best effort – im Fehlerfall nichts crashen lassen
        fs, fe = int(scene.frame_start), int(scene.frame_end)
        scene["_kc_repeat_series"] = {
            int(f): int(v)
            for f, v in mapping.items()
            if fs <= int(f) <= fe
        }
    try:
        _tag_redraw()
    except Exception:
        pass

# Neuer Name in deinem Branch:
def record_repeat_bulk_map(scene, mapping: dict[int, int]) -> None:
    return record_repeat_series_bulk(scene, mapping)

# -----------------------------------------------------------------------------
# Reader: vereinheitlichte Sicht auf die Serie als Dict {abs_frame: int}
# -----------------------------------------------------------------------------
def get_repeat_series_map(scene) -> dict[int, int]:
    """Liefert die Repeat-Serie als Mapping {abs_frame: int}, egal ob intern als
    Liste (frame_start-basiert) oder als Dict gespeichert."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return {}
    data = scene.get("_kc_repeat_series")
    if isinstance(data, dict):
        out: dict[int, int] = {}
        for k, v in data.items():
            try:
                out[int(k)] = int(v)
            except Exception:
                continue
        return out
    if isinstance(data, (list, tuple)):
        fs = int(getattr(scene, "frame_start", 1))
        out: dict[int, int] = {}
        for i, v in enumerate(data):
            try:
                out[fs + i] = int(v)
            except Exception:
                continue
        return out
    return {}



def ensure_repeat_scope_props() -> None:
    """Stellt sicher, dass die RNA-Properties existieren (idempotent)."""
    return

