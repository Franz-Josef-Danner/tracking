# SPDX-License-Identifier: GPL-2.0-or-later
import bpy
from gpu.types import GPUBatch, GPUShader
import gpu
from math import isfinite

_HANDLE = None

# Simple 2D shader
VERT_SRC = '''
in vec2 pos;
uniform mat4 ModelViewProjectionMatrix;
void main() { gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }
'''
FRAG_SRC = '''
uniform vec4 color;
out vec4 FragColor;
void main() { FragColor = color; }
'''

def _get_series(scene):
    data = scene.get("_kc_repeat_series")
    return list(data) if isinstance(data, list) else []

def _ensure_series_len(scene):
    fs, fe = scene.frame_start, scene.frame_end
    n = max(0, int(fe - fs + 1))
    series = _get_series(scene)
    if len(series) != n:
        series = ([0.0] * n) if n > 0 else []
        scene["_kc_repeat_series"] = series
    return n

def _box_coords(rx, ry, width, height):
    x0, y0 = rx, ry
    x1, y1 = rx + width, ry + height
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

def _polyline(coords, shader, color):
    fmt = gpu.types.GPUVertFormat()
    pid = fmt.attr_add(id="pos", comp_type='F32', len=2, fetch_mode='FLOAT')
    vbo = gpu.types.GPUVertBuf(format=fmt, len=len(coords))
    vbo.attr_fill(id=pid, data=coords)
    batch = GPUBatch(type='LINE_STRIP', buf=vbo)
    shader.bind()
    shader.uniform_float("color", color)
    batch.program_set(shader)
    batch.draw(shader)

def _tri_fan(coords, shader, color):
    fmt = gpu.types.GPUVertFormat()
    pid = fmt.attr_add(id="pos", comp_type='F32', len=2, fetch_mode='FLOAT')
    vbo = gpu.types.GPUVertBuf(format=fmt, len=len(coords))
    vbo.attr_fill(id=pid, data=coords)
    batch = GPUBatch(type='TRI_FAN', buf=vbo)
    shader.bind()
    shader.uniform_float("color", color)
    batch.program_set(shader)
    batch.draw(shader)

def draw_callback():
    ctx = bpy.context
    if not ctx or not ctx.area or ctx.area.type != 'CLIP_EDITOR':
        return
    scn = ctx.scene
    if not scn or not getattr(scn, "kc_show_repeat_scope", False):
        return

    region = ctx.region
    if not region or region.type != 'WINDOW':
        return

    # Properties
    height_px = max(50, int(getattr(scn, "kc_repeat_scope_height", 140)))
    bottom_px = max(0, int(getattr(scn, "kc_repeat_scope_bottom", 24)))
    margin_px = max(4, int(getattr(scn, "kc_repeat_scope_margin_x", 12)))

    # Box geometry
    x0 = float(margin_px)
    x1 = float(max(0, region.width - margin_px))
    width = max(0.0, x1 - x0)
    y0 = float(min(region.height - 1, bottom_px))
    y1 = float(min(region.height, y0 + height_px))
    height = max(0.0, y1 - y0)
    if width < 10.0 or height < 10.0:
        return

    # Data + normalization
    n = _ensure_series_len(scn)
    if n == 0:
        return
    series = _get_series(scn)
    if not series:
        return
    vmax = max(series) if series else 0.0
    if not isfinite(vmax) or vmax <= 0.0:
        vmax = 1.0

    shader = GPUShader(VERT_SRC, FRAG_SRC)

    # Background (semi-transparent)
    bg = _box_coords(x0, y0, width, height)
    _tri_fan(bg, shader, (0.05, 0.05, 0.05, 0.35))

    # Border
    border = bg + [bg[0]]
    _polyline(border, shader, (0.9, 0.9, 0.9, 0.75))

    # Clip drawing to box
    gpu.state.scissor_test_set(True)
    gpu.state.scissor_set(int(x0), int(y0), int(width), int(height))

    # Series as line across full scene-length (frames mapped to box width)
    if n == 1:
        xs = [x0, x1]
        ys = [y0, y0]
    else:
        step = width / float(n - 1)
        xs = [x0 + i * step for i in range(n)]
        ys = [y0 + (float(v) / vmax) * (height - 2.0) for v in series]
    coords = [(x, y) for x, y in zip(xs, ys)]
    if len(coords) >= 2:
        gpu.state.line_width_set(1.0)
        _polyline(coords, shader, (1.0, 1.0, 1.0, 0.95))
    # Optional: current-frame cursor inside the scope box (mapped to scene range)
    try:
        if getattr(scn, "kc_repeat_scope_show_cursor", True) and n >= 1:
            fs, fe = int(scn.frame_start), int(scn.frame_end)
            fc = int(getattr(scn, "frame_current", fs))
            denom = max(1, fe - fs)  # avoid div/0
            t = (fc - fs) / float(denom)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            cx = x0 + t * width
            cursor = [(cx, y0), (cx, y1)]
            _polyline(cursor, shader, (0.9, 0.8, 0.2, 0.95))
    except Exception:
        pass

    gpu.state.scissor_test_set(False)

def _add_handler():
    global _HANDLE
    if _HANDLE is None:
        _HANDLE = bpy.types.SpaceClipEditor.draw_handler_add(draw_callback, (), 'WINDOW', 'POST_PIXEL')

def _remove_handler():
    global _HANDLE
    if _HANDLE is not None:
        bpy.types.SpaceClipEditor.draw_handler_remove(_HANDLE, 'WINDOW')
        _HANDLE = None

def enable_repeat_scope():
    _add_handler()

def disable_repeat_scope():
    _remove_handler()

def is_scope_enabled():
    return _HANDLE is not None
