import bpy
from bpy.props import IntProperty


class CLIP_PT_kaiserlich_tracker(bpy.types.Panel):
    bl_label = "Kaiserlich Tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and getattr(space, 'clip', None) is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        # Logging: aktueller Wert bevor gezeichnet wird
        try:
            val = getattr(scene, 'kaiserlich_marker_per_frame', 'N/A')
            print(f"[Kaiserlich][UI][draw] kaiserlich_marker_per_frame = {val}")
        except Exception as e:
            print(f"[Kaiserlich][UI][draw][WARN] Zugriff auf Property fehlgeschlagen: {e}")
        layout.prop(scene, "kaiserlich_marker_per_frame")
        layout.operator("clip.kaiserlich_detect_cyclus", text="Detect Cyclus")


def register():
    if not hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        bpy.types.Scene.kaiserlich_marker_per_frame = IntProperty(
            name="Marker per Frame",
            default=25,
            min=1,
            description="Zielanzahl Marker pro Frame (±10% Toleranz)"
        )
        print("[Kaiserlich][UI][register] Scene Property 'kaiserlich_marker_per_frame' angelegt (default=25)")
    else:
        print("[Kaiserlich][UI][register] Scene Property 'kaiserlich_marker_per_frame' existiert bereits – wird nicht erneut angelegt")
    bpy.utils.register_class(CLIP_PT_kaiserlich_tracker)
    print("[Kaiserlich][UI][register] Panel 'CLIP_PT_kaiserlich_tracker' registriert")


def unregister():
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_tracker)
    print("[Kaiserlich][UI][unregister] Panel 'CLIP_PT_kaiserlich_tracker' deregistriert")
    if hasattr(bpy.types.Scene, 'kaiserlich_marker_per_frame'):
        try:
            del bpy.types.Scene.kaiserlich_marker_per_frame
            print("[Kaiserlich][UI][unregister] Scene Property 'kaiserlich_marker_per_frame' entfernt")
        except Exception as e:
            print(f"[Kaiserlich][UI][unregister][WARN] Entfernen der Property fehlgeschlagen: {e}")
    else:
        print("[Kaiserlich][UI][unregister] Scene Property 'kaiserlich_marker_per_frame' war nicht gesetzt")