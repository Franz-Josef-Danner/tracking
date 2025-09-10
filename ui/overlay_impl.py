# -----------------------------------------------------------------------------
# Adaptive Tick-Berechnung für das Overlay
# -----------------------------------------------------------------------------
def _compute_tick_step(view_min: float, view_max: float) -> float:
    """Tick-Abstand basierend auf dem Sichtbereich."""
    try:
        vrange = float(view_max) - float(view_min)
    except Exception:
        vrange = 0.0
    if vrange <= 0.0:
        return 1.0
    return vrange / 10.0


def _iter_ticks(view_min: float, view_max: float):
    """Generiert Tick-Positionen innerhalb des Sichtbereichs."""
    step = _compute_tick_step(view_min, view_max)
    eps = step * 1e-6
    import math as _m
    start = _m.ceil((view_min - eps) / step) * step
    t = start
    max_ticks = 1000
    count = 0
    while t <= view_max + eps and count < max_ticks:
        yield t
        t += step
        count += 1


def _format_tick(value: float, step: float) -> str:
    """Formatiert Labels abhängig von der Schrittweite."""
    if step >= 1.0:
        return f"{value:.0f}"
    import math as _m
    decimals = min(2, max(1, int(_m.ceil(-_m.log10(step))) + 1))
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(value)


def draw_solve_graph_impl():
    try:
        import bpy, math as _m, blf
        import gpu
        from gpu_extras.batch import batch_for_shader
    except Exception:
        return

    scn = getattr(bpy.context, "scene", None)
    if not scn or not getattr(scn, "kaiserlich_solve_graph_enabled", False):
        return

    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False))

    # BLF size helper (4.4 vs <4.4)
    def _blf_size(fid: int, sz: int) -> None:
        try:
            blf.size(fid, sz)
        except TypeError:
            try:
                blf.size(fid, sz, 72)
            except Exception:
                pass

    coll = getattr(scn, "kaiserlich_solve_err_log", [])
    seq = sorted((it.attempt, it.value) for it in coll if it.value == it.value)
    has_data = bool(seq)

    # Viewport fallback
    try:
        _vx, _vy, W, H = gpu.state.viewport_get()
    except Exception:
        region = getattr(bpy.context, "region", None)
        if not region:
            return
        W, H = region.width, region.height

    pad = 16
    gw, gh = min(320, W - 2*pad), 80
    yaxis_w = 42
    ox, oy = W - gw - pad, pad

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # Rahmen
    box = [(ox, oy), (ox+gw, oy), (ox+gw, oy+gh), (ox, oy+gh)]
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.35)); batch.draw(shader)

    def _draw_title():
        title = "Average Trend"
        font_id = 0
        try:
            _blf_size(font_id, 12)
            tw, th = blf.dimensions(font_id, title)
            tx = ox + yaxis_w
            ty = min(oy + gh + 6, H - th - 2)
            tx = max(tx, 0)
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, tx, ty, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, title)
            blf.disable(font_id, blf.SHADOW)
        except Exception:
            pass

    if not has_data:
        try:
            _draw_title()
            font_id = 0
            _blf_size(font_id, 11)
            txt = "No data yet"
            tw, th = blf.dimensions(font_id, txt)
            cx = ox + yaxis_w + (gw - yaxis_w - tw) * 0.5
            cy = oy + (gh - th) * 0.5
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, cx, cy, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, txt)
            blf.disable(font_id, blf.SHADOW)
        except Exception:
            pass
        return

    # kumulativer Durchschnitt, letzte 10
    vals = [v for _, v in seq]
    avg_vals = []
    s = 0.0
    for i, v in enumerate(vals, 1):
        s += float(v)
        avg_vals.append(s / i)
    take_vals = avg_vals[-10:]

    vmin, vmax = (min(take_vals), max(take_vals)) if take_vals else (0.0, 1.0)
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-12

    n = len(take_vals)
    ln = max(1, n - 1)
    coords = []
    for i, val in enumerate(take_vals):
        x = ox + yaxis_w + (i / ln) * (gw - yaxis_w)
        y = oy + ((val - vmin) / (vmax - vmin)) * gh
        coords.append((x, y))

    # Y-Achse adaptiv
    try:
        step = _compute_tick_step(vmin, vmax)
        ticks = list(_iter_ticks(vmin, vmax))

        yaxis_x = ox + yaxis_w
        batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, oy), (yaxis_x, oy+gh)]})
        shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.5)); batch.draw(shader)

        font_id = 0
        _blf_size(font_id, 11)
        for tv in ticks:
            rel = (tv - vmin) / (vmax - vmin)
            y = oy + rel * gh
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x-6, y), (yaxis_x, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.8)); batch.draw(shader)
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, y), (ox+gw, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.15)); batch.draw(shader)

            lbl = _format_tick(tv, step)
            lx = ox + 4
            ly = y - 6
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, lx, ly, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, lbl)
            blf.disable(font_id, blf.SHADOW)
    except Exception:
        pass

    # Linie
    if len(coords) == 1:
        coords.append((coords[0][0] + 1, coords[0][1]))

    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    _reset_width = False
    try:
        gpu.state.line_width_set(2.0)
        _reset_width = True
    except Exception:
        pass
    try:
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
        batch.draw(shader)
    except Exception:
        pass

    _draw_title()

    if _reset_width:
        try: gpu.state.line_width_set(1.0)
        except Exception: pass
