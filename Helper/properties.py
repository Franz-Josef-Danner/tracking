"""Scene properties + helpers for the Repeat Scope overlay."""
import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty
from importlib import import_module
from typing import Dict

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

    # Optional: Fade-Step als Scene-Property (wird in Helper.jump_to_frame gelesen)
    if not hasattr(Scene, "kc_repeat_fade_step"):
        Scene.kc_repeat_fade_step = IntProperty(
            name="Fade-Step (Frames)",
            description="Stufiger Abfall der Wiederholungen: alle N Frames −1",
            default=5, min=1, max=50,
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
                # ID-Props speichern Schlüssel als STRING -> zurück zu int
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
        m: Dict[int, int] = get_repeat_map(scene)
        m[int(frame)] = int(fval)
        # Blender ID-Props: Schlüssel müssen Strings sein
        scene["_kc_repeat_map"] = {str(k): int(v) for k, v in m.items()}
        try:
            print(f"[RepeatMap] single_write frame={int(frame)} val={int(fval)} size={len(m)}")
        except Exception:
            pass
        _tag_redraw()


def record_repeat_bulk_map(scene, repeat_map: dict[int, int]) -> None:
    """Bulk-Merge einer {frame->count} Map in Scene-Serie/Map.
    Merge-Regel: MAX(Current, New). Out-of-range Frames werden ignoriert.
    Loggt Statistik und triggert Redraw.
    """
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None or not isinstance(repeat_map, dict) or not repeat_map:
        print("[RepeatMap] bulk_merge skipped (no scene or empty map)")
        return

    fs, fe = int(scene.frame_start), int(scene.frame_end)
    n = max(0, fe - fs + 1)
    if n <= 0:
        print("[RepeatMap] bulk_merge skipped (invalid frame range)")
        return

    # Serie initialisieren / sanieren
    series = scene.get("_kc_repeat_series")
    if not isinstance(series, list) or len(series) != n:
        series = [0.0] * n

    # Aktuelle Map holen
    cur_map = get_repeat_map(scene)

    changed = 0
    unchanged = 0
    written_frames: list[int] = []
    vmax = 0

    for k, v in repeat_map.items():
        try:
            f = int(k)
            nv = max(0, int(v))
        except Exception:
            continue
        if f < fs or f > fe:
            continue
        idx = f - fs
        cv = int(series[idx]) if 0 <= idx < n else 0
        mv = int(cur_map.get(f, 0))
        merged = max(cv, nv)
        if merged != cv:
            series[idx] = float(merged)
            changed += 1
        else:
            unchanged += 1
        if merged > mv:
            cur_map[f] = merged
        vmax = max(vmax, merged)
        written_frames.append(f)

    scene["_kc_repeat_series"] = series
    # Blender ID-Props: Schlüssel müssen Strings sein
    scene["_kc_repeat_map"] = {str(k): int(v) for k, v in cur_map.items()}

    if written_frames:
        fmin, fmax = min(written_frames), max(written_frames)
        # Log-Ausgabe: Anzahl, Range, Änderungen, Max-Wert der Merge-Session
        print(
            f"[RepeatMap] bulk_merge write_frames={len(written_frames)} "
            f"range={fmin}..{fmax} changed={changed} unchanged={unchanged} vmax={vmax} "
            f"(stored_keys={len(cur_map)})"
        )
    else:
        print("[RepeatMap] bulk_merge had no in-range frames")
    _tag_redraw()
