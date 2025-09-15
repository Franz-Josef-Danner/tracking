"""Scene properties + helpers for Repeat-SSOT (ohne Grafik-Overlay)."""
import bpy
from bpy.props import BoolProperty, IntProperty
from typing import Dict


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


def register():
    """Register Scene properties (ohne Overlay)."""
    Scene = bpy.types.Scene

    # Debug-Schalter für Repeat/Fade-Logs
    Scene.kc_debug_repeat = BoolProperty(
        name="Repeat-Debug",
        description="Ausführliche Log-Ausgaben für Jump/Fade/Merge aktivieren",
        default=True,
    )

    # Fade-Step als Scene-Property (von Helper.jump_to_frame gelesen)
    if not hasattr(Scene, "kc_repeat_fade_step"):
        Scene.kc_repeat_fade_step = IntProperty(
            name="Fade-Step (Frames)",
            description="Stufiger Abfall der Wiederholungen: alle N Frames −1",
            default=5,
            min=1,
            max=50,
        )


def unregister():
    """Unregister Scene properties (ohne Overlay)."""
    Scene = bpy.types.Scene
    for attr in (
        "kc_debug_repeat",
        "kc_repeat_fade_step",
    ):
        if hasattr(Scene, attr):
            delattr(Scene, attr)


__all__ = (
    "register",
    "unregister",
    "record_repeat_count",
    "record_repeat_bulk_map",
    "get_repeat_value",
    "get_repeat_map",
)


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


def get_repeat_value(scene, frame: int) -> int:
    """Liest den Repeat-Wert (int) aus der Series-SSOT."""
    if scene is None:
        try:
            scene = bpy.context.scene
        except Exception:
            return 0
    if scene is None:
        return 0
    fs = int(scene.frame_start)
    fe = int(scene.frame_end)
    n = max(0, fe - fs + 1)
    series = scene.get("_kc_repeat_series")
    if not isinstance(series, list) or len(series) != n:
        return 0
    idx = int(frame) - fs
    if 0 <= idx < n:
        return int(series[idx])
    return 0


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
        # Für Map-Darstellung synchron halten (nur non-zero)
        m = scene.get("_kc_repeat_map", {}) or {}
        m[str(int(frame))] = int(series[idx])
        scene["_kc_repeat_map"] = m
        _dbg(scene, f"[RepeatMap][set] frame={int(frame)} {int(before)}→{int(value)} (series_len={len(series)})")


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
