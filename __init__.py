import bpy
from .UI.ui import KAISERLICHTRACKER_PT_panel
from .Operator.detect_operator import KAISERLICHTRACKER_OT_detect_cycle
from .Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle
from .UI.ui import ui as ui_module   # <— neu: explizit importieren

classes = (
    KAISERLICHTRACKER_OT_detect_cycle,
    KAISERLICHTRACKER_OT_track_cycle,
    KAISERLICHTRACKER_PT_panel,
)

def register():
    # 1) ZUERST die UI-Properties anlegen
    try:
        ui_module.register()
    except Exception as e:
        print(f"[Kaiserlich Tracker] Warnung: UI-Properties konnten nicht registriert werden: {e}")

    # 2) Dann Klassen registrieren (Panel erst jetzt!)
    for cls in classes:
        bpy.utils.register_class(cls)

    # 3) Weitere Properties
    bpy.types.Scene.kaiserlich_markers_per_frame = bpy.props.IntProperty(
        name="Marker per Frame",
        description="Zielanzahl Marker pro Frame",
        default=25,
        min=1,
        soft_min=1,
    )

def unregister():
    # Reihenfolge invertieren:
    # erst Klassen deregistrieren ...
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # ... dann Scene-Props sauber entfernen
    if hasattr(bpy.types.Scene, "kaiserlich_markers_per_frame"):
        del bpy.types.Scene.kaiserlich_markers_per_frame

    try:
        ui_module.unregister()
    except Exception:
        pass

if __name__ == "__main__":
    register()
