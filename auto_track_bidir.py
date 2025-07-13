import bpy
import logging

logger = logging.getLogger(__name__)

class TRACK_OT_auto_track_bidir(bpy.types.Operator):
    """Track ``TRACK_`` markers backward and forward from the current frame."""

    bl_idname = "clip.auto_track_bidir"
    bl_label = "Auto Track Bidirektional"
    bl_description = (
        "Trackt ausgewählte Marker zuerst rückwärts, dann vorwärts, "
        "und kehrt zum Startframe zurück"
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'CLIP_EDITOR'

    def execute(self, context):
        clip_editor = context.space_data
        clip = clip_editor.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Marker vorhanden")
            return {'CANCELLED'}

        active_obj = clip.tracking.objects.active
        track_list = active_obj.tracks
        track_sel = [t for t in track_list if t.name.startswith("TRACK_")]
        for t in track_list:
            t.select = t in track_sel
        if not track_sel:
            self.report({'WARNING'}, "Keine TRACK_ Marker gefunden")
            return {'CANCELLED'}
        logger.info("Tracking %d TRACK_ Marker", len(track_sel))

        def track_range(track):
            frames = [m.frame for m in track.markers]
            return (min(frames), max(frames)) if frames else (None, None)

        ranges_before = {t.name: track_range(t) for t in track_sel}
        for name, rng in ranges_before.items():
            print(f"Vor Tracking {name}: {rng}")

        scene = context.scene
        current_frame = scene.frame_current
        logger.info("Aktueller Frame: %s", current_frame)

        logger.info("Starte Rückwärts-Tracking...")
        bpy.ops.clip.track_markers(backwards=True, sequence=True)
        logger.info("Rückwärts-Tracking abgeschlossen.")

        ranges_after_back = {t.name: track_range(t) for t in track_sel}
        for name, rng in ranges_after_back.items():
            print(f"Nach Rueckwaerts {name}: {rng}")

        # Zurück zum ursprünglichen Frame springen
        scene.frame_current = current_frame
        logger.info("Zurück zum Ausgangsframe: %s", current_frame)

        logger.info("Starte Vorwärts-Tracking...")
        bpy.ops.clip.track_markers(backwards=False, sequence=True)
        logger.info("Vorwärts-Tracking abgeschlossen.")

        ranges_after_forward = {t.name: track_range(t) for t in track_sel}
        for name, rng in ranges_after_forward.items():
            print(f"Nach Vorwaerts {name}: {rng}")

        # Sicherstellen, dass Frame wieder korrekt gesetzt ist
        scene.frame_current = current_frame
        logger.info("Finaler Frame gesetzt auf: %s", current_frame)

        return {'FINISHED'}


class TRACK_PT_auto_track_panel(bpy.types.Panel):
    """UI Panel für den bidirektionalen Auto-Track"""
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = "Auto Track"

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.auto_track_bidir", icon='TRACKING_FORWARDS')

classes = [
    TRACK_OT_auto_track_bidir,
    TRACK_PT_auto_track_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
