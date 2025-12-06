import bpy

# --------------------------------------------------------------
# Interner Addon-State Reset (falls benötigt)
# --------------------------------------------------------------
# Hinweis: Falls du globale Variablen hast (z.B. repeat counter,
# bootstrap values, tracking caches etc.), importiere sie hier
# und setze sie zurück.
#
# Beispiel:
#
# from .master_stop_check import reset_stop_check_state
#
# Danach in reset_internal_state(): reset_stop_check_state()
#
# --------------------------------------------------------------

def reset_internal_state():
    """Reset aller temporären Variablen und Addon-internen States."""
    # Optional: Hier eigene Reset-Funktionen registrieren.
    # Placeholder (absichtlich leer, damit es keine Fehlfunktion erzeugt)
    pass


# --------------------------------------------------------------
# UI Refresh
# --------------------------------------------------------------
def refresh_ui():
    """Erzwingt ein vollständiges UI-Redraw in Blender."""
    wm = bpy.context.window_manager

    # Alle Fensterbereiche neu zeichnen
    for window in wm.windows:
        for area in window.screen.areas:
            area.tag_redraw()

    # Sicherstellen, dass UI nicht verzögert refresht
    bpy.ops.wm.redraw_timer(type='DRAW', iterations=1)


# --------------------------------------------------------------
# Dependency Graph Refresh
# --------------------------------------------------------------
def refresh_depsgraph(context):
    """Synchronisiert UI/Scene mit validem Depsgraph-Zustand."""
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()


# --------------------------------------------------------------
# Movie Clip Tracking Cache Reset (Clip-Editor relevant)
# --------------------------------------------------------------
def reset_tracking_cache(context):
    """Setzt Solve-/Tracking-Cache zurück. Wichtig nach Backjump, Löschen oder Track-Recovery."""
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)

    if clip is None:
        return

    tracking_obj = clip.tracking.objects.active

    # Reset Reconstruction Cache (Solve, Errors, Reprojection Map)
    if tracking_obj.reconstruction.is_valid:
        tracking_obj.reconstruction.reset()


# --------------------------------------------------------------
# Scene Refresh (Frame State Harmonisierung)
# --------------------------------------------------------------
def refresh_playhead(context):
    """Erzwingt einen konsistenten Frame-Reload."""
    scene = context.scene
    scene.frame_set(scene.frame_current)


# --------------------------------------------------------------
# Hauptfunktion: Extern aufrufbar
# --------------------------------------------------------------
def reset_and_refresh(context):
    """
    Führt einen vollständigen Addon-Reset-Refresh aus:
    - internen Addon-State reinigen
    - Tracking Cache zurücksetzen
    - Playhead/Depsgraph aktualisieren
    - UI refreshen

    Danach ist Blender in einem "sauberen" Zustand für den nächsten Tracking-Schritt.
    """

    reset_internal_state()
    reset_tracking_cache(context)
    refresh_playhead(context)
    refresh_depsgraph(context)
    refresh_ui()