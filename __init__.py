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
from .UI.ui import KAISERLICHTRACKER_PT_panel
from .Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle
from .Operator.auto_calibrate_operator import KAISERLICHTRACKER_OT_auto_calibrate_modal
from .Operator.detect_adapt_operator import KAISERLICHTRACKER_OT_detect_adapt
from .Operator.track_operator_backwards import KAISERLICHTRACKER_OT_track_cycle_backwards
from .Operator.master_operator import KAISERLICHTRACKER_OT_master_operator
classes = (
    KAISERLICHTRACKER_OT_track_cycle,
    KAISERLICHTRACKER_OT_auto_calibrate_modal,
    KAISERLICHTRACKER_OT_detect_adapt,
    KAISERLICHTRACKER_OT_track_cycle_backwards,
    KAISERLICHTRACKER_OT_master_operator,
    KAISERLICHTRACKER_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Property für Eingabefeld
    bpy.types.Scene.kaiserlich_markers_per_frame = bpy.props.IntProperty(
        name="Marker per Frame",
        description="Zielanzahl Marker pro Frame",
        default=25,
        min=1,
        soft_min=1,
    )

    # UI-Properties registrieren
    try:
        from .UI import ui
        ui.register()
    except Exception as e:
        print(f"[Kaiserlich Tracker] Warnung: UI-Properties konnten nicht registriert werden: {e}")
        
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.kaiserlich_markers_per_frame

    try:
        from .UI import ui
        ui.unregister()
    except Exception:
        pass
if __name__ == "__main__":
    register()
