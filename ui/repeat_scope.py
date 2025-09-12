# SPDX-License-Identifier: GPL-2.0-or-later
# Kaiserlich Repeat-Scope – robuste Handler-API + Fallback-Zeichnung
import bpy, gpu
try:
    from gpu_extras.batch import batch_for_shader
except Exception:
    batch_for_shader = None  # Fallback, falls gpu_extras fehlt

# Globaler Handle (idempotent, auch bei mehrfacher Registrierung sicher)
_REPEAT_SCOPE_HANDLE = globals().get("_REPEAT_SCOPE_HANDLE", None)

def is_scope_enabled() -> bool:
    """Gibt True zurück, wenn der Draw-Handler aktiv ist."""
    return globals().get("_REPEAT_SCOPE_HANDLE") is not None

def _get_draw_fn():
    """
    Sucht die eigentliche Zeichenfunktion des Repeat-Scopes im Modul.
    Nimmt die erste gefundene aus der bekannten Namensliste.
    """
    for name in ("_draw_callback", "draw_callback", "_repeat_scope_draw", "draw", "on_draw"):
        fn = globals().get(name)
        if callable(fn):
            return fn
    return None

def _fallback_draw():
    """Minimaler Fallback-Renderer (Box unten), falls Custom-Draw scheitert."""
    area = bpy.context.area
    region = bpy.context.region
    if not area or area.type != 'CLIP_EDITOR' or not region or region.type != 'WINDOW':
        return
    try:
        sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    except Exception:
        return
    if not batch_for_shader:
        return
    w, h = region.width, region.height
    x0, y0 = 12, 24
    x1, y1 = max(20, w - 12), min(h - 4, 24 + 140)
    # Hintergrund
    coords = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(sh, 'TRI_FAN', {"pos": coords})
    sh.bind(); sh.uniform_float("color", (0, 0, 0, 0.25)); batch.draw(sh)
    # Rahmen
    coords = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    batch = batch_for_shader(sh, 'LINE_STRIP', {"pos": coords})
    sh.bind(); sh.uniform_float("color", (1, 1, 1, 0.5)); batch.draw(sh)

def _wrapped_draw():
    """
    Ruft die eigentliche Zeichenroutine auf; bei Fehlern zeichnet der Fallback.
    """
    fn = _get_draw_fn()
    if fn:
        try:
            fn()
            return
        except Exception as e:
            print("[RepeatScope] draw failed – fallback used:", e)
    _fallback_draw()

def _tag_redraw():
    win = getattr(bpy.context, "window", None)
    scr = getattr(win, "screen", None)
    if not scr:
        return
    for a in scr.areas:
        if a.type == 'CLIP_EDITOR':
            a.tag_redraw()

def enable_repeat_scope(enable: bool = True):
    """
    Registriert/entfernt den Draw-Handler idempotent und triggert Redraw.
    Diese Funktion wird vom UI-Toggle (Scene.kc_show_repeat_scope) aufgerufen.
    """
    global _REPEAT_SCOPE_HANDLE
    if enable and globals().get("_REPEAT_SCOPE_HANDLE") is None:
        _REPEAT_SCOPE_HANDLE = bpy.types.SpaceClipEditor.draw_handler_add(
            _wrapped_draw, (), 'WINDOW', 'POST_PIXEL'
        )
        globals()["_REPEAT_SCOPE_HANDLE"] = _REPEAT_SCOPE_HANDLE
        print("[RepeatScope] handler registered")
        _tag_redraw()
    elif (not enable) and globals().get("_REPEAT_SCOPE_HANDLE") is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(globals()["_REPEAT_SCOPE_HANDLE"], 'WINDOW')
        finally:
            globals()["_REPEAT_SCOPE_HANDLE"] = None
        print("[RepeatScope] handler removed")
        _tag_redraw()
