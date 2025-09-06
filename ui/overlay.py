import bpy

# Draw-Handler-Handle
_handle = None

# Wir nutzen die bestehende Overlay-Zeichnung aus dem alten __init__.py,
# aber kapseln sie in ein Modul. Import erst zur Laufzeit, damit gpu verfügbar ist.
def _draw_solve_graph_proxy():
    from .overlay_impl import draw_solve_graph_impl
    draw_solve_graph_impl()

def register():
    global _handle
    if _handle is None:
        try:
            _handle = bpy.types.SpaceClipEditor.draw_handler_add(
                _draw_solve_graph_proxy, (), 'WINDOW', 'POST_PIXEL'
            )
        except Exception:
            _handle = None

def unregister():
    global _handle
    if _handle is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_handle, 'WINDOW')
        except Exception:
            pass
        _handle = None
