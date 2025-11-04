import bpy

def set_progress(title: str = None, value: float = None):
    """Setzt den UI-Ladebalken-Status.
    title: Optionaler Text für Statusanzeige.
    value: Fortschritt (0.0–1.0)."""
    scene = bpy.context.scene
    if not scene:
        return

    if title is not None:
        scene.kaiserlich_progress_title = title

    if value is not None:
        scene.kaiserlich_progress_value = max(0.0, min(1.0, value))

    # UI aktualisieren (sofortiges Redraw)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                area.tag_redraw()
