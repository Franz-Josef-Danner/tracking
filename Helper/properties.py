"""Scene properties + helpers for the Repeat Scope overlay."""
import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty
from importlib import import_module

__all__ = (
    "register",
    "unregister",
    "record_repeat_count",
    "record_repeat_bulk_map",
    "get_repeat_map",
)


def _kc_request_overlay_redraw(context):
    try:
        mod = import_module("..ui.repeat_scope", __package__)
        enable = bool(getattr(context.scene, "kc_show_repeat_scope", False))
        mod.enable_repeat_scope(enable, source="prop_update")
    except Exception:
        # defensiv: während Startup/Prefs keine harten Fehler
        pass


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
        default=140,
        min=40, max=800,
    )
    Scene.kc_repeat_scope_bottom = IntProperty(
        name="Abstand unten",
        description="Abstand vom unteren Rand (Pixel)",
        default=24,
        min=0, max=2000,
    )
    Scene.kc_repeat_scope_margin_x = IntProperty(
        name="Rand X",
        description="Horizontaler Innenabstand (Pixel)",
        default=12,
        min=0, max=2000,
    )
    Scene.kc_repeat_scope_show_cursor = BoolProperty(
        name="Cursorlinie",
        description="Aktuellen Frame als Linie anzeigen",
        default=True,
    )
    Scene.kc_repeat_scope_levels = IntProperty(
        name="Höhenstufen",
        description="Anzahl der diskreten Höhenstufen für das Repeat-Scope (Quantisierung der Kurve)",
        default=36,
        min=2, max=200,
        update=lambda self, ctx: _kc_request_overlay_redraw(ctx),
    )
    
    # Optional: Fade-Stufe (wird von jump_to_frame.py gelesen; Default 5)
    Scene.kc_repeat_fade_step = IntProperty(
        name="Fade-Stufe (Frames)",
        description="In so vielen Frame-Schritten fällt der Wiederholungswert um 1",
        default=5, min=1, max=120,
        update=lambda self, ctx: _kc_request_overlay_redraw(ctx),
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


def get_repeat_map(scene=None) -> dict[int, int]:
    """Return mapping abs frame -> repeat count (robust)."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return {}
    if scene is None:
        return {}

    m = scene.get("_kc_repeat_map")
    if isinstance(m, dict):
        out: dict[int, int] = {}
        for k, v in m.items():
            try:
                ik, iv = int(k), int(v)
            except Exception:
                continue
            if iv:
                out[ik] = iv
        return out

    # Fallback: alte Liste
    series = scene.get("_kc_repeat_series")
    if isinstance(series, list):
        fs = int(scene.frame_start)
        out: dict[int, int] = {}
        for i, v in enumerate(series):
            try:
                iv = int(v)
            except Exception:
                continue
            if iv:
                out[fs + i] = iv
        return out

    return {}


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
        fval = float(max(0.0, fval))
        series[idx] = fval
        scene["_kc_repeat_series"] = series

        # Parallel: Map pflegen
        m = get_repeat_map(scene)
        m[int(frame)] = int(fval)
        scene["_kc_repeat_map"] = m
        _tag_redraw()


def record_repeat_bulk_map(scene, repeat_map: dict[int, int]) -> None:
    """Schreibt mehrere (frame -> repeat) Einträge in einem Rutsch.
    - Clamp auf Szenenrange
    - Pro Frame wird der MAX aus bestehendem Wert und neuem Wert übernommen
    - Aktualisiert Serie UND Map konsistent
    - Triggert Redraw genau einmal
    """
    if not repeat_map:
        return
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return

    fs, fe = int(scene.frame_start), int(scene.frame_end)
    n = max(0, fe - fs + 1)
    if n <= 0:
        return

    series = list(scene.get("_kc_repeat_series") or [])
    if len(series) != n:
        series = [0.0] * n

    # Bestehende Map holen (robust) und kopieren
    existing = get_repeat_map(scene)
    updated = dict(existing)

    changed = 0
    written = 0
    min_f = None
    max_f = None

    for f_abs, v_in in repeat_map.items():
        try:
            f = int(f_abs)
            v = int(v_in)
        except Exception:
            continue
        if v <= 0:
            continue
        if f < fs or f > fe:
            continue  # außerhalb der Szene ignorieren

        idx = f - fs
        cur_series = float(series[idx]) if 0 <= idx < n else 0.0
        cur_map = int(existing.get(f, 0))
        new_v = float(max(cur_series, v, cur_map))
        if new_v > cur_series:
            series[idx] = new_v
            changed += 1
        # Map immer auf MAX heben
        if int(new_v) > cur_map:
            updated[f] = int(new_v)
        else:
            # auch wenn Serie unverändert blieb, sicherstellen, dass Key existiert
            updated.setdefault(f, int(new_v))

        written += 1
        min_f = f if min_f is None else min(min_f, f)
        max_f = f if max_f is None else max(max_f, f)

    scene["_kc_repeat_series"] = series
    scene["_kc_repeat_map"] = updated
    _tag_redraw()

    # Logging
    print(
        f"[RepeatScope][WRITE] bulk frames={written}, changed_series={changed}, "
        f"range={min_f}..{max_f}, levels={getattr(scene, 'kc_repeat_scope_levels', 36)}"
    )
