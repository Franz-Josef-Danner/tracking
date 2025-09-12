+# SPDX-License-Identifier: GPL-2.0-or-later
+import bpy
+from gpu.types import GPUBatch, GPUShader
+import gpu
+from math import isfinite

_HANDLE = None

VERT_SRC = '''
in vec2 pos;
uniform mat4 ModelViewProjectionMatrix;
void main() { gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0); }
'''
FRAG_SRC = '''
out vec4 FragColor;
void main() { FragColor = vec4(1.0, 1.0, 1.0, 1.0); }
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

def draw_callback():
    ctx = bpy.context
    if not ctx or not ctx.area or ctx.area.type != 'CLIP_EDITOR':
        return
    scn = ctx.scene
    if not scn or not getattr(scn, "kc_show_repeat_overlay", False):
        return

    n = _ensure_series_len(scn)
    if n == 0:
        return
    series = _get_series(scn)
    if not series:
        return

    vmin = 0.0
    vmax = max(series) if series else 0.0
    if not isfinite(vmax) or vmax <= 0.0:
        vmax = 1.0

    region = ctx.region
    rx0, rx1 = 0.0, float(region.width)
    ry0, ry1 = 0.0, float(region.height)

    height_px = max(60, int(getattr(scn, "kc_repeat_overlay_height", 120)))
    ry1 = float(min(region.height, height_px))

    if n == 1:
        xs = [rx0, rx1]
        ys = [ry0, ry0]
    else:
        step = (rx1 - rx0) / float(n - 1)
        xs = [rx0 + i * step for i in range(n)]
        ys = [ry0 + (float(v) - vmin) / (vmax - vmin) * (ry1 - ry0) for v in series]

    coords = [(x, y) for x, y in zip(xs, ys)]
    if len(coords) < 2:
        return

    shader = GPUShader(VERT_SRC, FRAG_SRC)
    fmt = gpu.types.GPUVertFormat()
    pos_id = fmt.attr_add(id="pos", comp_type='F32', len=2, fetch_mode='FLOAT')
    vbo = gpu.types.GPUVertBuf(format=fmt, len=len(coords))
    vbo.attr_fill(id=pos_id, data=coords)
    batch = GPUBatch(type='LINE_STRIP', buf=vbo)

    gpu.state.scissor_test_set(True)
    gpu.state.scissor_set(0, region.height - int(ry1), int(rx1), int(ry1))
    shader.bind()
    batch.program_set(shader)
    batch.draw(shader)
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

def enable_repeat_overlay():
    _add_handler()

def disable_repeat_overlay():
    _remove_handler()

def is_overlay_enabled() -> bool:
    return _HANDLE is not None
