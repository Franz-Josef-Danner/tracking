# SPDX-License-Identifier: GPL-2.0-or-later
# Kaiserlich Repeat-Scope Overlay: Visualisiert Repeat-Zähler mit stufigem Fade-Out.
# Änderungen:
# - Draw-Enable prüft zusätzlich auf Sticky-IDProp („_kc_repeat_scope_sticky“)
# - Zusätzliche Diagnose-Logs für Sticky-Status und Data-Readiness
# - UI-Autostart bleibt erhalten, nutzt aber lokale Prüfung

from __future__ import annotations
import bpy
import blf
import bgl
from math import floor

_HANDLE = None
_REGISTERED = False
_NO_DATA_LOGGED = False  # einmalige "no data" Diagnose pro Session
_DATA_READY_LOGGED = False  # einmalige Diagnose bei erstem Daten-Draw
_STICKY_KEY = "_kc_repeat_scope_sticky"


def _is_enabled_local(scn: "bpy.types.Scene") -> bool:
    """Overlay gilt als aktiv, wenn entweder die UI-Property an ist
    ODER Sticky (IDProp) explizit gesetzt wurde."""
    try:
        ui_flag = bool(getattr(scn, "kc_show_repeat_scope", False))
    except Exception:
        ui_flag = False
    sticky = bool(scn.get(_STICKY_KEY, False))
    return ui_flag or sticky


def register() -> None:
    """UI-Modul registrieren und ggf. Handler auto-aktivieren."""
    global _REGISTERED
    _REGISTERED = True
    print("[Scope] register()")
    try:
        scn = bpy.context.scene
        if _is_enabled_local(scn):
            ensure_repeat_scope_handler(scn)
            print("[Scope] auto-ensure handler on register (enabled=True or sticky=True)")
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] auto-ensure on register failed: {e!r}")


def unregister() -> None:
    """UI-Modul deregistrieren und Handler entfernen."""
    global _REGISTERED
    _REGISTERED = False
    print("[Scope] unregister()")
    try:
        disable_repeat_scope_handler()
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler remove on unregister failed: {e!r}")

def _get_series_and_range(scn: bpy.types.Scene) -> tuple[list[float], int, int]:
    """Robust Serie + [fs, fe] ermitteln. Leere/inkonsistente Serie → []."""
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


def _draw_text(x: int, y: int, s: str, size: int = 14) -> None:
    try:
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glColor4f(1.0, 1.0, 1.0, 1.0)
        blf.position(0, x, y, 0)
        blf.size(0, size, 72)
        blf.draw(0, s)
    except Exception:
        pass
    finally:
        try:
            bgl.glDisable(bgl.GL_BLEND)
        except Exception:
            pass


def _sample_window(series: list[float], center_idx: int, radius: int = 10) -> tuple[float, int, int]:
    if not series:
        return 0.0, 0, 0
    lo = max(0, center_idx - radius)
    hi = min(len(series), center_idx + radius + 1)
    window = series[lo:hi]
    vmax = max(window) if window else 0.0
    return vmax, lo, hi - 1


def _draw_cursor_value_and_log(scn: bpy.types.Scene) -> None:
    series, fs, fe = _get_series_and_range(scn)
    if not series:
        return
    cur = int(getattr(scn, "frame_current", fs))
    if cur < fs or cur > fe:
        return
    idx = cur - fs
    val = series[idx]
    vmax, lo, hi = _sample_window(series, idx, radius=10)

    bottom = getattr(scn, "kc_repeat_scope_bottom", 24)
    margin_x = getattr(scn, "kc_repeat_scope_margin_x", 12)
    _draw_text(
        margin_x + 6,
        bottom + 6,
        f"Repeat {floor(val)}  (win max {floor(vmax)} @ {lo+fs}-{hi+fs})",
        size=13,
    )

    last = scn.get("_kc_scope_last_logged_frame")
    if last != cur:
        print(
            f"[Scope][Draw] frame={cur} val={floor(val)} window={lo+fs}..{hi+fs} vmax={floor(vmax)}"
        )
        scn["_kc_scope_last_logged_frame"] = cur

def _viewport_size() -> tuple[int, int]:
    """Ermittelt die Größe der aktiven CLIP_EDITOR Region zuverlässig."""
    reg = getattr(bpy.context, "region", None)
    if reg and hasattr(reg, "width") and hasattr(reg, "height"):
        return int(reg.width), int(reg.height)
    # Fallback: erste CLIP_EDITOR-WINDOW Region
    try:
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'CLIP_EDITOR':
                    r = next((rr for rr in a.regions if rr.type == 'WINDOW'), None)
                    if r:
                        return int(r.width), int(r.height)
    except Exception:
        pass
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
    if not scn:
        return
    ui_flag = bool(getattr(scn, "kc_show_repeat_scope", False))
    sticky = bool(scn.get(_STICKY_KEY, False))
    if not (ui_flag or sticky):
        return
    if not ui_flag and sticky:
        # Nur einmal pro Frame loggen, um Spam zu vermeiden
        last = scn.get("_kc_scope_last_sticky_frame")
        curf = int(getattr(scn, "frame_current", 0))
        if last != curf:
            print("[Scope][Sticky] UI-Flag off, aber sticky=True → zeichne trotzdem")
            scn["_kc_scope_last_sticky_frame"] = curf

    # Konfiguration aus Scene-Properties
    H_px = int(getattr(scn, "kc_repeat_scope_height", 140))
    bottom = int(getattr(scn, "kc_repeat_scope_bottom", 24))
    margin_x = int(getattr(scn, "kc_repeat_scope_margin_x", 12))
    show_cursor = bool(getattr(scn, "kc_repeat_scope_show_cursor", True))
    levels = int(getattr(scn, "kc_repeat_scope_levels", 36))

    series, fs, fe = _get_series_and_range(scn)

    W, H = _viewport_size()
    if W <= 0 or H <= 0:
        # kein gültiger Viewport – nichts zu zeichnen
        return

    ox = max(0, margin_x)
    ow = max(1, W - 2 * margin_x)
    oy = max(0, bottom)
    # Clamp, falls Scope außerhalb liegen würde
    oh = max(8, min(H_px, max(8, H - oy - 4)))

    # Hintergrundrahmen: immer zeichnen (auch ohne Daten)
    try:
        shader_box = gpu.shader.from_builtin('UNIFORM_COLOR')
        box = [(ox, oy), (ox + ow, oy), (ox + ow, oy + oh), (ox, oy + oh)]
        batch_box = batch_for_shader(shader_box, 'LINE_LOOP', {"pos": box})
        shader_box.bind(); shader_box.uniform_float("color", (1, 1, 1, 0.28)); batch_box.draw(shader_box)
    except Exception:
        pass

    # Wenn keine Daten vorhanden, früh aussteigen – aber einmalig diagnostizieren
    global _NO_DATA_LOGGED, _DATA_READY_LOGGED
    if not series:
        if not _NO_DATA_LOGGED:
            _NO_DATA_LOGGED = True
            try:
                print("[Scope][Draw] no series yet – drawing frame only (enable handler OK, waiting for data)")
            except Exception:
                pass
        return

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

    _draw_cursor_value_and_log(scn)

    # Einmalige „ready“-Diagnose
    if not _DATA_READY_LOGGED:
        _DATA_READY_LOGGED = True
        try:
            nz = sum(1 for v in series if v)
            print(f"[Scope][Draw] data ready: len={len(series)} nonzero={nz} viewport={W}x{H}")
        except Exception:
            pass


def ensure_repeat_scope_handler(_scene=None) -> None:
    """Sicherstellen, dass der Draw-Handler aktiv ist."""
    global _HANDLE
    if _HANDLE is not None:
        return
    try:
        _HANDLE = bpy.types.SpaceClipEditor.draw_handler_add(
            _draw_callback, tuple(), 'WINDOW', 'POST_PIXEL'
        )
        print("[Scope] handler added")
        try:
            for w in bpy.context.window_manager.windows:
                for a in w.screen.areas:
                    if a.type == 'CLIP_EDITOR':
                        for r in a.regions:
                            if r.type == 'WINDOW':
                                r.tag_redraw()
            print("[Scope] redraw tag propagated to CLIP_EDITOR windows")
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler add failed: {e!r}")


def disable_repeat_scope_handler() -> None:
    """Draw-Handler entfernen (falls aktiv)."""
    global _HANDLE
    if _HANDLE is None:
        return
    try:
        bpy.types.SpaceClipEditor.draw_handler_remove(_HANDLE, 'WINDOW')
        print("[Scope] handler removed")
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler remove failed: {e!r}")
    _HANDLE = None


def enable_repeat_scope(enable: bool, *, source: str = "api") -> None:
    """Kompatibilitäts-Wrapper für ältere Aufrufer."""
    if enable:
        ensure_repeat_scope_handler()
    else:
        disable_repeat_scope_handler()
    print(f"[KC] enable_repeat_scope({bool(enable)}) source={source}")


def disable_repeat_scope(*, source: str = "api") -> None:
    """Bequemer Alias für enable_repeat_scope(False)."""
    return enable_repeat_scope(False, source=source)

