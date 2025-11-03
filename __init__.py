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
# ---- Operator & UI Imports -------------------------------------------------
from .UI.ui import KAISERLICHTRACKER_PT_panel
from .Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle
from .Operator.shorttest_operator import KAISERLICHTRACKER_OT_shorttest_operator
from .Operator.deep_test_operator import KAISERLICHTRACKER_OT_deep_test_operator
from .Operator.detect_adapt_operator import KAISERLICHTRACKER_OT_detect_adapt
from .Operator.track_operator_backwards import KAISERLICHTRACKER_OT_track_cycle_backwards
from .Operator.resolve_operator import KAISERLICHTRACKER_OT_resolve_operator, KAISERLICHTRACKER_OT_solve_modal
from .Operator.master_operator import KAISERLICHTRACKER_OT_master_operator
from .Operator.Master.master_track_operator import KAISERLICHTRACKER_OT_master_track_cycle
from .Operator.Master.master_shorttest_operator import KAISERLICHTRACKER_OT_master_shorttest_operator
from .Operator.Master.master_deep_test_operator import KAISERLICHTRACKER_OT_master_deep_test_operator
from .Operator.Master.master_detect_adapt_operator import KAISERLICHTRACKER_OT_master_detect_adapt
from .Operator.Master.master_track_operator_backwards import KAISERLICHTRACKER_OT_master_track_cycle_backwards
from .Operator.Master.master_cycle_operator import KAISERLICHTRACKER_OT_master_cycle_operator
from .Operator.Master.master_resolve_operator import KAISERLICHTRACKER_OT_master_resolve_operator, KAISERLICHTRACKER_OT_master_solve_modal

# ---- Klassenliste ----------------------------------------------------------
classes = (
    KAISERLICHTRACKER_PT_panel,
    KAISERLICHTRACKER_OT_track_cycle,
    KAISERLICHTRACKER_OT_shorttest_operator,
    KAISERLICHTRACKER_OT_deep_test_operator,
    KAISERLICHTRACKER_OT_detect_adapt,
    KAISERLICHTRACKER_OT_track_cycle_backwards,
    KAISERLICHTRACKER_OT_resolve_operator,
    KAISERLICHTRACKER_OT_solve_modal,
    KAISERLICHTRACKER_OT_master_track_cycle,
    KAISERLICHTRACKER_OT_master_shorttest_operator,
    KAISERLICHTRACKER_OT_master_deep_test_operator,
    KAISERLICHTRACKER_OT_master_detect_adapt,
    KAISERLICHTRACKER_OT_master_track_cycle_backwards,
    KAISERLICHTRACKER_OT_master_cycle_operator,
    KAISERLICHTRACKER_OT_master_operator,
    KAISERLICHTRACKER_OT_master_resolve_operator,
    KAISERLICHTRACKER_OT_master_solve_modal,
)

# ---- Register / Unregister -------------------------------------------------
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
    bpy.types.Scene.kaiserlich_frames_per_track = bpy.props.IntProperty(
        name="Frames per Track",
        description="Mindestanzahl an Frames, die ein Track haben muss, um beim Cleanup nicht gelöscht zu werden",
        default=25,
        min=0,
        soft_min=0,
    )
    bpy.types.Scene.max_error_value = bpy.props.FloatProperty(
        name="Max Error Value",
        description="Tracks mit einem Solve-Error über diesem Wert werden herausgefiltert",
        default=2.0,
        min=0.5,
        soft_min=1.0,
        step=0.1,
        precision=3,
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

    # Property entfernen
    if hasattr(bpy.types.Scene, "kaiserlich_markers_per_frame"):
        del bpy.types.Scene.kaiserlich_markers_per_frame
    if hasattr(bpy.types.Scene, "kaiserlich_frames_per_track"):
        del bpy.types.Scene.kaiserlich_frames_per_track
    if hasattr(bpy.types.Scene, "max_error_value"):
        del bpy.types.Scene.max_error_value

    try:
        from .UI import ui
        ui.unregister()
    except Exception:
        pass

if __name__ == "__main__":
    register()
