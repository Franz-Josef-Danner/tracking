import bpy
from .. import gpu, batch_for_shader

_solve_graph_handle = None


def _draw_solve_graph():
    if gpu is None:
        return
    import blf
    import math as _m
    scn = getattr(bpy.context, "scene", None)

    # --- BLF Compatibility: Blender 4.4 nutzt blf.size(font_id, size).
    # Ältere Versionen akzeptieren blf.size(font_id, size, dpi).
    def _blf_size(fid: int, sz: int) -> None:
        try:
            blf.size(fid, sz)             # Blender ≥ 4.4
        except TypeError:
            try:
                blf.size(fid, sz, 72)     # Fallback für ältere Versionen
            except Exception:
                pass

    if not scn or not getattr(scn, "kaiserlich_solve_graph_enabled", False):
        return
    dbg = bool(getattr(scn, "kaiserlich_debug_graph", False))
    if dbg:
        pass  # removed print
    coll = getattr(scn, "kaiserlich_solve_err_log", [])
    # Chronologisch (ältester→neuester), NaN ignorieren
    seq = sorted((it.attempt, it.value) for it in coll if it.value == it.value)
    has_data = bool(seq)
    if dbg:
        pass  # removed print
    # Viewport-Maße robust beschaffen (Region ist nicht garantiert gesetzt)
    try:
        _vx, _vy, W, H = gpu.state.viewport_get()
    except Exception:
        region = getattr(bpy.context, "region", None)
        if not region:
            return
        W, H = region.width, region.height
    if dbg:
        pass  # removed print
    pad = 16
    gw, gh = min(320, W - 2 * pad), 80
    # Platz links für Y-Achse reservieren (Achse + Labels)
    yaxis_w = 42
    ox, oy = W - gw - pad, pad
    if dbg:
        pass  # removed print
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    # Rahmen
    box = [(ox, oy), (ox + gw, oy), (ox + gw, oy + gh), (ox, oy + gh)]
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": box})
    shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.35)); batch.draw(shader)

    # --- Titel-Helper: ÜBER der Box (links), mit BLF-Shadow ---
    def _draw_title():
        title = "Average Trend"
        font_id = 0
        try:
            _blf_size(font_id, 12)
            tw, th = blf.dimensions(font_id, title)
            # Position: oberhalb der Box, linksbündig an der Y-Achse
            tx = ox + yaxis_w
            ty = oy + gh + 6
            # Clipping-Schutz (nicht oberhalb des Viewports rauszeichnen)
            ty = min(ty, H - th - 2)
            tx = max(tx, 0)
            # Shadow/Outline für Lesbarkeit
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)       # weich, schwarz
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, tx, ty, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, title)
            blf.disable(font_id, blf.SHADOW)
            if dbg:
                pass  # removed print
        except Exception as ex:
            if dbg:
                pass  # removed print

    # Wenn keine Daten vorliegen: Hinweis zeichnen und früh aussteigen
    if not has_data:
        try:
            # Titel trotzdem zeigen (oben links in der Box)
            _draw_title()
            font_id = 0
            _blf_size(font_id, 11)
            txt = "No data yet"
            tw, th = blf.dimensions(font_id, txt)
            cx = ox + yaxis_w + (gw - yaxis_w - tw) * 0.5
            cy = oy + (gh - th) * 0.5
            # Shadow für Lesbarkeit
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

    # --- Gleitender kumulativer Durchschnitt für das Overlay ---
    vals = [v for _, v in seq]
    avg_vals = []
    s = 0.0
    for i, v in enumerate(vals, 1):
        s += float(v)
        avg_vals.append(s / i)
    # Nur die letzten 10 Punkte (chronologisch) – mit Durchschnittswerten
    take_vals = avg_vals[-10:]
    # Skala ausschließlich aus den letzten 10 Werten ableiten
    vmin, vmax = (min(take_vals), max(take_vals)) if take_vals else (0.0, 1.0)
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1e-12
    if dbg:
        pass  # removed print
        pass  # removed print
    n = len(take_vals)
    ln = max(1, n - 1)  # vermeidet Div/0, erlaubt 1-Punkt-Stub
    coords = []
    for i, val in enumerate(take_vals):
        x = ox + yaxis_w + (i / ln) * (gw - yaxis_w)
        y = oy + ((val - vmin) / (vmax - vmin)) * gh
        coords.append((x, y))
    if dbg:
        pass  # removed print
    # Y-Achse mit Ticks + numerischen Labels (links)
    try:
        # Feste Schrittweite: 5er-Sprünge
        step = 5.0
        # Ticks strikt im sichtbaren Datenbereich halten
        tick0 = _m.ceil(vmin / step) * step  # erster Tick >= vmin
        tickN = _m.floor(vmax / step) * step  # letzter Tick <= vmax
        ticks = []
        if tickN >= tick0:
            count = int(_m.floor((tickN - tick0) / step)) + 1
            count = min(count, 64)
            ticks = [tick0 + i * step for i in range(count)]
        if dbg:
            pass  # removed print
            pass  # removed print
        # Achsenlinie
        yaxis_x = ox + yaxis_w
        batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, oy), (yaxis_x, oy + gh)]})
        shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.5)); batch.draw(shader)
        # Ticks + Labels + horizontale Gridlines
        font_id = 0
        _blf_size(font_id, 11)
        # 5er-Sprünge → ganzzahlige Labels
        prec = 0
        _fmt = f"{{:.{prec}f}}"
        for tv in ticks:
            rel = (tv - vmin) / (vmax - vmin)
            y = oy + rel * gh
            # Tick
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x - 6, y), (yaxis_x, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.8)); batch.draw(shader)
            # Gridline dezent
            batch = batch_for_shader(shader, 'LINES', {"pos": [(yaxis_x, y), (ox + gw, y)]})
            shader.bind(); shader.uniform_float("color", (1, 1, 1, 0.15)); batch.draw(shader)
            # Label
            lbl = _fmt.format(tv)
            lx = ox + 4
            ly = y - 6
            # Shadow/Outline für Lesbarkeit
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 255)
            blf.shadow_offset(font_id, 1, -1)
            blf.position(font_id, lx, ly, 0)
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, lbl)
            blf.disable(font_id, blf.SHADOW)
        if dbg and ticks:
            y0 = oy + ((ticks[0] - vmin) / (vmax - vmin)) * gh - 6
            y1 = oy + ((ticks[-1] - vmin) / (vmax - vmin)) * gh - 6
            pass  # removed print
            pass  # removed print
    except Exception:
        pass
    # Kurve
    # Bei nur einem Punkt einen 1px-Stub zeichnen, damit sichtbar
    if len(coords) == 1:
        coords.append((coords[0][0] + 1, coords[0][1]))
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    # Sichtbarkeit verbessern: 2px Linienbreite (sofern verfügbar)
    _reset_width = False
    try:
        gpu.state.line_width_set(2.0)
        _reset_width = True
    except Exception:
        pass
    # >>> FEHLENDER DRAW-CALL (fix) <<<
    try:
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
        batch.draw(shader)
    except Exception:
        pass
    # Titel zuletzt zeichnen (oberste Ebene, nicht überdeckt)
    _draw_title()
    # Abschluss-Log sauber außerhalb des try/except-Blocks
    if dbg:
        pass  # removed print
    # Linienstärke zurücksetzen
    if _reset_width:
        try:
            gpu.state.line_width_set(1.0)
        except Exception:
            pass


def register():
    global _solve_graph_handle
    if _solve_graph_handle is None and gpu is not None:
        try:
            _solve_graph_handle = bpy.types.SpaceClipEditor.draw_handler_add(
                _draw_solve_graph, (), 'WINDOW', 'POST_PIXEL'
            )
        except Exception:
            _solve_graph_handle = None


def unregister():
    global _solve_graph_handle
    if _solve_graph_handle is not None and gpu is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_solve_graph_handle, 'WINDOW')
        except Exception:
            pass
        _solve_graph_handle = None

