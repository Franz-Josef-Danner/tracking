import bpy
import logging

logger = logging.getLogger(__name__)

class TRACKING_OT_delete_short_tracks_with_prefix(bpy.types.Operator):
    bl_idname = "tracking.delete_short_tracks_with_prefix"
    bl_label = "Delete Short Tracks with Prefix"
    bl_description = "Delete tracking tracks with prefix 'TRACK_' and less than 25 frames"

    def execute(self, context):
        logger.info("=== [Operator gestartet: TRACKING_OT_delete_short_tracks_with_prefix] ===")

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "No clip loaded")
            logger.info("❌ Kein Movie Clip geladen – Abbruch.")
            return {'CANCELLED'}
        logger.info(f"🎬 Clip: {clip.name}")

        active_obj = clip.tracking.objects.active
        tracks = active_obj.tracks
        logger.info(f"📷 Aktives Objekt: {active_obj.name} — {len(tracks)} Tracks vorhanden")

        # Filter nach Präfix und Marker-Anzahl
        tracks_to_delete = [
            t for t in tracks
            if t.name.startswith("TRACK_") and len(t.markers) < 25
        ]

        logger.info("🎯 Tracks mit Präfix 'TRACK_' und < 25 Frames:")
        for t in tracks_to_delete:
            logger.info(f"   - {t.name} ({len(t.markers)} Frames)")

        for track in tracks:
            track.select = track in tracks_to_delete

        if not tracks_to_delete:
            logger.info("ℹ️ Keine passenden Tracks gefunden – beende.")
            self.report({'INFO'}, "No short tracks found with prefix 'TRACK_'")
            return {'CANCELLED'}

        logger.info("🔎 Suche nach CLIP_EDITOR Bereich für Operator...")
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                logger.info("✅ Kontext bereit – führe delete_track() aus")
                                with context.temp_override(
                                    area=area,
                                    region=region,
                                    space_data=space
                                ):
                                    bpy.ops.clip.delete_track()
                                logger.info(f"🗑️ {len(tracks_to_delete)} Track(s) gelöscht.")
                                self.report({'INFO'}, f"Deleted {len(tracks_to_delete)} short tracks with prefix 'TRACK_'")
                                logger.info("=== [Operator erfolgreich beendet] ===")
                                return {'FINISHED'}

        logger.info("❌ Kein geeigneter Clip Editor Bereich gefunden.")
        self.report({'ERROR'}, "No Clip Editor area found.")
        logger.info("=== [Operator abgebrochen] ===")
        return {'CANCELLED'}

class TRACKING_PT_custom_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Custom Tracking Tools'

    def draw(self, context):
        layout = self.layout
        layout.operator("tracking.delete_short_tracks_with_prefix")

def register():
    bpy.utils.register_class(TRACKING_OT_delete_short_tracks_with_prefix)
    bpy.utils.register_class(TRACKING_PT_custom_panel)
    logger.info("🔧 Operator & Panel registriert")

def unregister():
    bpy.utils.unregister_class(TRACKING_OT_delete_short_tracks_with_prefix)
    bpy.utils.unregister_class(TRACKING_PT_custom_panel)
    logger.info("🧹 Operator & Panel entfernt")

if __name__ == "__main__":
    register()
