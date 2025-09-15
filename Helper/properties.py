"""Scene properties + helpers for the Repeat Scope overlay + Repeat-Debug."""
import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty
from typing import Dict

_STICKY_KEY = "_kc_repeat_scope_sticky"

__all__ = (
    "register",
    "unregister",
    "record_repeat_count",
    "record_repeat_bulk_map",
    "get_repeat_map",
    "enable_repeat_scope",
    "set_repeat_scope_sticky",
    "is_repeat_scope_enabled",
    "redraw_clip_editors",
)


def redraw_clip_editors() -> None:
    """Redraw all Clip Editor windows."""
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


def _dbg_enabled(scn) -> bool:
    try:
        return bool(getattr(scn, "kc_debug_repeat", True))
    except Exception:
        return True


def _dbg(scn, msg: str) -> None:
    if _dbg_enabled(scn):
        try:
            print(msg)
        except Exception:
            pass


def _kc_request_overlay_redraw(context):
    try:
        redraw_clip_editors()
    except Exception:
        # defensiv: während Startup/Prefs keine harten Fehler
        pass


def _kc_update_repeat_scope(_self, context):
    try:
        _kc_request_overlay_redraw(context)
    except Exception:
        pass


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
    # Debug-Schalter für alle Repeat/Fade-Logs
    Scene.kc_debug_repeat = BoolProperty(
        name="Repeat-Debug",
        description="Ausführliche Log-Ausgaben für Jump/Fade/Merge aktivieren",
        default=True,
    )

    # Layout
    Scene.kc_repeat_scope_height = IntProperty(
        name="Höhe",
        description="Höhe des Repeat-Scope (Pixel)",
        default=140,
        min=40,
        max=800,
    )
    Scene.kc_repeat_scope_bottom = IntProperty(
        name="Bottom",
        description="Abstand vom unteren Rand (Pixel)",
        default=22,
        min=0,
        max=400,
    )
    Scene.kc_repeat_scope_margin_x = IntProperty(
        name="Margin X",
        description="Abstand zu linken/rechten Rändern (Pixel)",
        default=16,
        min=0,
        max=200,
    )
    Scene.kc_repeat_scope_show_cursor = BoolProperty(
        name="Cursor",
        description="Frame-Cursor im Repeat-Scope anzeigen",
        default=True,
    )
    Scene.kc_repeat_scope_levels = IntProperty(
        name="Levels",
        description="Höhenstufen für Wiederholungen",
        default=4,
        min=1,
        max=20,
    )

    # Optional: Fade-Step als Scene-Property (wird in Helper.jump_to_frame gelesen)
    if not hasattr(Scene, "kc_repeat_fade_step"):
        Scene.kc_repeat_fade_step = IntProperty(
            name="Fade-Step (Frames)",
            description="Stufiger Abfall der Wiederholungen: alle N Frames −1",
            default=5,
            min=1,
            max=50,
        )


def unregister():
    """Unregister Repeat-Scope Scene properties."""
    Scene = bpy.types.Scene
    for attr in (
        "kc_show_repeat_scope",
        "kc_debug_repeat",
        "kc_repeat_scope_height",
        "kc_repeat_scope_bottom",
        "kc_repeat_scope_margin_x",
        "kc_repeat_scope_show_cursor",
        "kc_repeat_scope_levels",
        "kc_repeat_fade_step",
    ):
        if hasattr(Scene, attr):
            delattr(Scene, attr)


def is_repeat_scope_enabled(scn: bpy.types.Scene) -> bool:
    return bool(getattr(scn, "kc_show_repeat_scope", False))


def set_repeat_scope_sticky(scn: bpy.types.Scene, sticky: bool, *, source: str = "api") -> None:
    scn[_STICKY_KEY] = bool(sticky)
    _dbg(scn, f"[KC] set_repeat_scope_sticky({bool(sticky)}) source={source}")


def enable_repeat_scope(
    scn: bpy.types.Scene,
    enabled: bool,
    *,
    source: str = "api",
    sticky: bool | None = None,
) -> None:
    if sticky is not None:
        set_repeat_scope_sticky(scn, sticky, source=source)
    scn.kc_show_repeat_scope = bool(enabled)
    _dbg(scn, f"[KC] enable_repeat_scope({bool(enabled)}) source={source} sticky={scn.get(_STICKY_KEY)}")
    try:
        _kc_request_overlay_redraw(bpy.context)
    except Exception as e:  # noqa: BLE001
        _dbg(scn, f"[KC][WARN] repeat_scope handler toggle failed: {e!r}")


def get_repeat_map(scene=None) -> dict[int, int]:
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return {}
    if scene is None:
        return {}
    m = scene.get("_kc_repeat_map", {})
    try:
        return {int(k): int(v) for k, v in m.items()}
    except Exception:
        return {}


def record_repeat_count(scene, frame, value) -> None:
    """Speichert den Repeat-Wert für einen absoluten Frame in Scene-ID-Props.
    Serie: scene['_kc_repeat_series'] (Float-Liste in Frame-Range)."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return

    # Serie vorbereiten
    fs = int(scene.frame_start)
    fe = int(scene.frame_end)
    n = max(0, fe - fs + 1)
    series = scene.get("_kc_repeat_series")
    if not isinstance(series, list) or len(series) != n:
        series = [0.0] * n

    # MAX-Merge: niemals verringern
    idx = int(frame) - fs
    cur = float(series[idx]) if 0 <= idx < n else 0.0
    if value > cur:
        before = cur
        series[idx] = float(value)
        scene["_kc_repeat_series"] = series
        # Für Map-Darstellung synchron halten
        m = scene.get("_kc_repeat_map", {}) or {}
        m[str(int(frame))] = int(series[idx])
        scene["_kc_repeat_map"] = m
        _dbg(scene, f"[RepeatMap][set] frame={int(frame)} {int(before)}→{int(value)} (series_len={len(series)})")
        _kc_request_overlay_redraw(bpy.context)


def record_repeat_bulk_map(scene, repeat_map: Dict[int, int]) -> None:
    """Schreibt eine Menge Frame→Wert in einem Rutsch (MAX-Merge) mit Diagnose-Logs."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return
    if scene is None:
        return

    fs = int(scene.frame_start)
    fe = int(scene.frame_end)
    n = max(0, fe - fs + 1)
    series = scene.get("_kc_repeat_series")
    if not isinstance(series, list) or len(series) != n:
        series = [0.0] * n

    # MAX-Merge für jedes Element
    changed = 0
    min_f, max_f = None, None
    for f, v in (repeat_map or {}).items():
        try:
            f = int(f)
            v = int(v)
        except Exception:
            continue
        idx = f - fs
        if not (0 <= idx < n):
            continue
        cur = float(series[idx])
        if v > cur:
            series[idx] = float(v)
            changed += 1
            min_f = f if min_f is None else min(min_f, f)
            max_f = f if max_f is None else max(max_f, f)
            if _dbg_enabled(scene):
                print(f"[RepeatMap][merge] frame={f} {int(cur)}→{int(v)}")

    scene["_kc_repeat_series"] = series
    # Map parallel pflegen (nur non-zero)
    out_map: Dict[str, int] = {}
    for i, val in enumerate(series):
        iv = int(val)
        if iv:
            out_map[str(fs + i)] = iv
    scene["_kc_repeat_map"] = out_map
    if changed:
        nz = sum(1 for v in series if v)
        _dbg(scene, f"[RepeatMap][bulk] changed={changed} range={min_f}..{max_f} nonzero={nz} series_len={len(series)}")
        _kc_request_overlay_redraw(bpy.context)

