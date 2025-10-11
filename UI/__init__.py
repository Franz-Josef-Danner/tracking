"""
Initialisierung des Kaiserlich Tracker Add‑ons.

Dieses Modul definiert die Add‑on Metadaten (``bl_info``), importiert
die UI‑Panels und Operatoren und registriert sie bei Blender.  Im
Gegensatz zur ursprünglichen Version wurden hier zusätzliche Klassen
aufgenommen, um die neue Auto‑Kalibrationsfunktion verfügbar zu
machen.  Außerdem werden die UI‑Properties (wie die Thresholds) über
``ui.register()`` initialisiert.
"""

bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz-Josef Danner",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich Tracker",
    "description": "Hilft beim Berechnen von Marker Parametern (Pattern/Search Größe) basierend auf Auflösung und gewünschter Marker-Dichte.",
    "category": "Tracking",
}

import bpy

# Importiere Panel und Operatoren
from .UI.ui import KAISERLICHTRACKER_PT_panel
from .Operator.detect_operator import KAISERLICHTRACKER_OT_detect_cycle
from .Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle
from .Operator.auto_calibrate_operator import KAISERLICHTRACKER_OT_auto_calibrate


# Reihenfolge der Registrierung: erst Operatoren, dann Panel
classes = (
    KAISERLICHTRACKER_OT_detect_cycle,
    KAISERLICHTRACKER_OT_track_cycle,
    KAISERLICHTRACKER_OT_auto_calibrate,
    KAISERLICHTRACKER_PT_panel,
)


def register() -> None:
    """Registriere alle Komponenten des Add‑ons."""
    for cls in classes:
        bpy.utils.register_class(cls)
    # Property für Eingabefeld Marker per Frame, falls noch nicht vorhanden
    bpy.types.Scene.kaiserlich_markers_per_frame = bpy.props.IntProperty(
        name="Marker per Frame",
        description="Zielanzahl Marker pro Frame",
        default=25,
        min=1,
        soft_min=1,
    )
    # UI-Properties registrieren (Schwellenwerte etc.)
    try:
        from .UI import ui
        ui.register()
    except Exception as e:
        print(f"[Kaiserlich Tracker] Warnung: UI-Properties konnten nicht registriert werden: {e}")


def unregister() -> None:
    """Deregistriere alle Komponenten des Add‑ons."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # Eingabefeld entfernen, falls vorhanden
    if hasattr(bpy.types.Scene, "kaiserlich_markers_per_frame"):
        del bpy.types.Scene.kaiserlich_markers_per_frame
    # UI-Properties deregistrieren
    try:
        from .UI import ui
        ui.unregister()
    except Exception:
        pass


if __name__ == "__main__":
    register()