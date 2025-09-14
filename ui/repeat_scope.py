# SPDX-License-Identifier: GPL-2.0-or-later
# Kaiserlich Repeat-Scope Overlay: Visualisiert Repeat-Zähler mit stufigem Fade-Out.
#
# - Liest scene['_kc_repeat_series'] (Float-Liste in Frame-Range)
# - Zeichnet eine normalisierte Kurve (Levels-Quantisierung) am unteren Rand
# - Cursor-Linie optional
# - Draw-Handler on/off via enable_repeat_scope()/disable_repeat_scope()

from __future__ import annotations
import bpy

_HDL_KEY = "_KC_REPEAT_SCOPE_HDL"

def _get_series_and_range(scn: bpy.types.Scene) -> tuple[list[float], int, int]:
    """Robust Serie + [fs, fe] ermitteln; leere Serie → []."""
    try:
        fs, fe = int(scn.frame_start), int(scn.frame_end)
        n = max(0, fe - fs + 1)
        if n <= 0:
            return [], fs, fe
        series = scn.get("_kc_repeat_series") or []
        if not isinstance(series, list) or len(series) != n:
            return [], fs, fe
        # Float-Cast + >=0 clamp
        out = []
        for v in series:
            try:
                fv = float(v)
            except Exception:
                fv = 0.0
            out.append(max(0.0, fv))
        return out, fs, fe
    except Exception:
        return [], 0, 0

def _viewport_size():
    """(W,H) robust ermitteln (GPU-Viewport oder Region-Fallback)."""
    try:
        import gpu  # noqa
        _vx, _vy, W, H = gpu.state.viewport_get()
        return int(W), int(H)
    except Exception:
        reg = getattr(bpy.context, "region", None)
        if reg:
            return int(getattr(reg, "width", 0) or 0), int(getattr(reg, "height", 0) or 0)
        return 0, 0

def _quantize(v: float, vmax: float, levels: int) -> float:
    """Quantisierung auf diskrete Levels (0..1)."""
    if vmax <= 1e-12:
        return 0.0
    x = max(0.0, v) / vmax
    if levels <= 1:
        return min(1.0, x)
    step = 1.0 / float(levels - 1)
    # Runde auf nächstliegende Stufe
    idx = round(x / step)
    return max(0.0, min(1.0, idx * step))

def _draw_callback():
    """POST_PIXEL Draw-Handler: zeichnet Serie als LINE_STRIP."""
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader
        import math as _m
    except Exception:
        return

    scn = getattr(bpy.context, "scene", None)
    if not scn or not bool(getattr(scn, "kc_show_repeat_scope", False)):
        return

    # Konfiguration aus Scene-Properties
    H_px = int(getattr(scn, "kc_repeat_scope_height", 140))
    bottom = int(getattr(scn, "kc_repeat_scope_bottom", 24))
    margin_x = int(getattr(scn, "kc_repeat_scope_margin_x", 12))
    show_cursor = bool(getattr(scn, "kc_repeat_scope_show_cursor", True))
    levels = int(getattr(scn, "kc_repeat_scope_levels", 36))

    series, fs, fe = _get_series_and_range(scn)
    if not series:
        return

    W, H = _viewport_size()
    if W <= 0 or H <= 0:
        return

    ox = max(0, margin_x)
    ow = max(1, W - 2 * margin_x)
    oy = max(0, bottom)
    oh = max(8, min(H_px, H - oy - 4))

    # Skalen
    vmax = max(series) if series else 1.0
    total = max(1, fe - fs)  # Range in Frames (min 1, um div/0 zu vermeiden)

    # Punkte berechnen (LINE_STRIP über gesamte Szene)
    coords = []
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    for i, v in enumerate(series):
        # x-Position: linear über Frames
        rel_x = i / float(total)
        x = ox + rel_x * ow
        # y-Position: quantisiert
        q = _quantize(v, vmax, levels)
        y = oy + q * oh
        coords.append((x, y))

    if not coords:
        return

    # Hintergrundrahmen (optional)
    try:
        box = [(ox, oy), (ox + ow, oy), (ox + ow, oy + oh), (ox, oy + oh)]
        batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
        shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.28)); batch.draw(shader)
    except Exception:
        pass

    # Kurve
    try:
        # SINGLE-POINT Edge-Case
        if len(coords) == 1:
            coords.append((coords[0][0] + 1, coords[0][1]))
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
        _reset = False
        try:
            gpu.state.line_width_set(2.0)
            _reset = True
        except Exception:
            pass
        shader.bind(); shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95)); batch.draw(shader)
        if _reset:
            try:
                gpu.state.line_width_set(1.0)
            except Exception:
                pass
    except Exception:
        pass

    # Cursor-Linie
    if show_cursor:
        try:
            cf = int(getattr(scn, "frame_current", fs))
            cf = max(fs, min(cf, fe))
            rel_x = (cf - fs) / float(total)
            cx = ox + rel_x * ow
            batch = batch_for_shader(shader, 'LINES', {"pos": [(cx, oy), (cx, oy + oh)]})
            shader.bind(); shader.uniform_float("color", (1.0, 1.0, 1.0, 0.55)); batch.draw(shader)
        except Exception:
            pass

def _store_handle(hdl) -> None:
    try:
        bpy.app.driver_namespace[_HDL_KEY] = hdl
    except Exception:
        pass

def _load_handle():
    try:
        return bpy.app.driver_namespace.get(_HDL_KEY)
    except Exception:
        return None

def enable_repeat_scope(enable: bool, *, source: str = "api") -> None:
    """Overlay ein-/ausschalten; mehrfach-idempotent; mit Logausgabe."""
    try:
        scn = bpy.context.scene
    except Exception:
        scn = None

    hdl = _load_handle()
    has_hdl = bool(hdl)

    if enable and not has_hdl:
        try:
            hdl = bpy.types.SpaceClipEditor.draw_handler_add(
                _draw_callback, tuple(), 'WINDOW', 'POST_PIXEL'
            )
            _store_handle(hdl)
            print(f"[KC] enable_repeat_scope(True) source={source}")
        except Exception as e:
            print(f"[KC] enable_repeat_scope failed: {e}")
            return
    elif (not enable) and has_hdl:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(hdl, 'WINDOW')
        except Exception:
            pass
        _store_handle(None)
        print(f"[KC] enable_repeat_scope(False) source={source}")
    else:
        # Keine Veränderung – dennoch transparent loggen
        print(f"[KC] enable_repeat_scope({bool(enable)}) source={source} (no-op)")

def disable_repeat_scope(*, source: str = "api") -> None:
    """Bequemer Alias für enable_repeat_scope(False)."""
    return enable_repeat_scope(False, source=source)

