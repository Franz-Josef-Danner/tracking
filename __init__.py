bl_info = {
    "name": "Kaiserlich Tracker",
    "author": "Franz Josef Danner",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "Clip Editor > Sidebar (N) > Kaiserlich",
    "description": "Einfaches Panel im Clip Editor mit Eingaben für Tracking",
    "category": "Tracking",
}

import bpy
from bpy.props import IntProperty, FloatProperty, CollectionProperty
from bpy.types import PropertyGroup, Panel

# Helper-Module (enthält CLIP_OT_bidirectional_track + register/unregister)
from .Helper import bidirectional_track
from .Operator.tracking_coordinator import CLIP_OT_tracking_coordinator

# --- PropertyGroup für Wiederhol-Frames ---
class RepeatEntry(PropertyGroup):
    frame: IntProperty(
        name="Frame",
        description="Frame-Index, der mehrfach zu wenige Marker hatte",
        default=0,
        min=0,
    )
    count: IntProperty(
        name="Count",
        description="Anzahl Wiederholungen für diesen Frame",
        default=0,
        min=0,
    )

# --- UI-Panel ---
class CLIP_PT_kaiserlich_panel(Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"
    bl_label = "Kaiserlich Tracker"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.label(text="Tracking Einstellungen")
        layout.prop(scene, "marker_frame")
        layout.prop(scene, "frames_track")
        layout.prop(scene, "error_track")
        layout.separator()
        layout.operator("clip.tracking_coordinator", text="Track")

# --- Registrierung ---
classes = (
    RepeatEntry,
    CLIP_PT_kaiserlich_panel,
    CLIP_OT_tracking_coordinator,
)

def register():
    # Erst die lokalen Klassen registrieren
    for cls in classes:
        bpy.utils.register_class(cls)

    # Dann Helper-Operator registrieren
    bidirectional_track.register()

    # CollectionProperty erst nach Registrierung von RepeatEntry anlegen
    bpy.types.Scene.repeat_frame = CollectionProperty(type=RepeatEntry)

    # UI-Eigenschaften
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker per Frame",
        default=25, min=10, max=50,
        description="Mindestanzahl Marker pro Frame"
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames per Track",
        default=25, min=5, max=100,
        description="Track-Länge in Frames"
    )
    bpy.types.Scene.error_track = FloatProperty(
        name="Error-Limit (px)",
        description="Maximale tolerierte Reprojektion in Pixeln",
        default=2.0, min=1.0, max=4.0,
    )

def unregister():
    # Properties löschen
    del bpy.types.Scene.repeat_frame
    del bpy.types.Scene.marker_frame
    del bpy.types.Scene.frames_track
    del bpy.types.Scene.error_track

    # Helper-Operator deregistrieren
    bidirectional_track.unregister()

    # Lokale Klassen deregistrieren
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
