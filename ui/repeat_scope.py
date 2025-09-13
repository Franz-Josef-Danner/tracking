# SPDX-License-Identifier: GPL-2.0-or-later
"""Draw handler and API for the Kaiserlich repeat scope overlay."""

import bpy
import gpu
import math
from typing import Dict
from gpu_extras.batch import batch_for_shader
from ..Helper.properties import get_repeat_map

# interner Handler
_HDL = None


def request_overlay_redraw(context: bpy.types.Context) -> None:
    """
    Externe Schnittstelle: Wird nach Bulk-Write der Repeat-Serie aufgerufen.
    Ziel: Draw-Handler neu rendern (Header/Region-Redraw).
    """
    win = context and context.window
    if not win:
        return
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type in {'WINDOW', 'HEADER'}:
                    region.tag_redraw()


def _get_repeat_series_for_view(scene: bpy.types.Scene) -> Dict[int, int]:
    return get_repeat_map(scene)


def _draw_scope() -> None:
    ctx = bpy.context
    area, region = ctx.area, ctx.region
    if not area or area.type != "CLIP_EDITOR" or not region or region.type != "WINDOW":
        return

    s = ctx.scene
    w, h = region.width, region.height

    # Szenen-Properties mit Defaults abholen (falls es sie noch nicht gibt)
    height = getattr(s, "kc_repeat_scope_height", 140)
    bottom = getattr(s, "kc_repeat_scope_bottom", 24)
    margin_x = getattr(s, "kc_repeat_scope_margin_x", 12)
    show_cur = getattr(s, "kc_repeat_scope_show_cursor", True)

    x0, y0 = margin_x, bottom
    x1, y1 = w - margin_x, min(h - 4, bottom + height)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return

    sh = gpu.shader.from_builtin("UNIFORM_COLOR")

    # Hintergrund
    bg = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(sh, "TRI_FAN", {"pos": bg})
    sh.bind()
    sh.uniform_float("color", (0, 0, 0, 0.25))
    batch.draw(sh)

    # Rahmen
    border = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    batch = batch_for_shader(sh, "LINE_STRIP", {"pos": border})
    sh.bind()
    sh.uniform_float("color", (1, 1, 1, 0.5))
    batch.draw(sh)

    # Datenserie
    fs, fe = s.frame_start, s.frame_end
    series_map = _get_repeat_series_for_view(s)
    if series_map:
        vmin = 0
        vmax = max(series_map.values())
    else:
        vmin = vmax = 0
    n = max(1, fe - fs + 1)
    seq = [int(series_map.get(fs + i, 0)) for i in range(n)]
    vmax = max(1, vmax)
    width, height_px = x1 - x0, y1 - y0

    # Quantisierung der Werte
    levels = max(2, int(getattr(s, "kc_repeat_scope_levels", 36)))
    denom = float(levels - 1)
    norm = [(v / vmax) if vmax else 0.0 for v in seq]
    qnorm = []
    for v in norm:
        vn = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
        step = math.floor(vn * levels)
        if step >= levels:
            step = levels - 1
        qnorm.append(step / denom)

    # Punkt-Liste aus quantisierten Werten
    pts = []
    Ln = max(1, len(qnorm) - 1)
    for i, qv in enumerate(qnorm):
        t = i / Ln
        px = x0 + t * width
        py = y0 + qv * height_px
        pts.append((px, py))
    batch = batch_for_shader(sh, "LINE_STRIP", {"pos": pts})
    sh.bind()
    sh.uniform_float("color", (0.8, 0.9, 1.0, 1.0))
    batch.draw(sh)

    # horizontale Hilfslinien gemäß Quantisierung
    tick_step = max(1, int(math.ceil(levels / 10)))
    for k in range(0, levels, tick_step):
        y = y0 + (k / denom) * height_px
        batch = batch_for_shader(sh, "LINES", {"pos": [(x0, y), (x1, y)]})
        sh.bind()
        sh.uniform_float("color", (1, 1, 1, 0.15))
        batch.draw(sh)

    # Cursor
    if show_cur:
        f = s.frame_current
        if fs <= f <= fe:
            t = (f - fs) / max(1, (fe - fs))
            cx = x0 + t * width
            batch = batch_for_shader(sh, "LINE_STRIP", {"pos": [(cx, y0), (cx, y1)]})
            sh.bind()
            sh.uniform_float("color", (1, 1, 1, 0.5))
            batch.draw(sh)


def enable_repeat_scope(on: bool = True, source: str = "api") -> None:
    """Öffentliche API – wird von UI/Props und beim Laden aufgerufen."""
    global _HDL
    print(f"[KC] enable_repeat_scope({on}) source={source}")
    if on:
        if _HDL is None:
            _HDL = bpy.types.SpaceClipEditor.draw_handler_add(
                _draw_scope, (), "WINDOW", "POST_PIXEL"
            )
    else:
        if _HDL is not None:
            try:
                bpy.types.SpaceClipEditor.draw_handler_remove(_HDL, "WINDOW")
            except Exception:
                pass
            _HDL = None


def disable_repeat_scope(source: str = "api") -> None:
    """Für Altcode, der ein explizites disable erwartet."""
    enable_repeat_scope(False, source=source)


def is_scope_enabled() -> bool:
    """Return True if the draw handler is currently registered."""
    return _HDL is not None

