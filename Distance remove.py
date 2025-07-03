import bpy
import mathutils

class CLIP_OT_remove_close_neu_markers(bpy.types.Operator):
    bl_idname = "clip.remove_close_neu_markers"
    bl_label = "NEU_-Marker löschen (zu nahe an GOOD_)"
    bl_description = "Löscht NEU_-Marker im aktuellen Frame, wenn sie zu nahe an GOOD_-Markern liegen"

    min_distance = 0.02  # 2% Bildbreite/Höhe im normierten Raum (0-1)

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "❌ Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        current_frame = context.scene.frame_current
        tracks = clip.tracking.tracks

        # Listen vorbereiten
        neu_tracks = [t for t in tracks if t.name.startswith("NEU_")]
        good_tracks = [t for t in tracks if t.name.startswith("GOOD_")]

        to_remove = []

        for neu in neu_tracks:
            neu_marker = neu.markers.find_frame(current_frame)
            if not neu_marker:
                continue
            neu_pos = mathutils.Vector(neu_marker.co)

            for good in good_tracks:
                good_marker = good.markers.find_frame(current_frame)
                if not good_marker:
                    continue
                good_pos = mathutils.Vector(good_marker.co)

                distance = (neu_pos - good_pos).length
                if distance < self.min_distance:
                    print(f"⚠️ {neu.name} ist zu nahe an {good.name} (Distanz: {distance:.5f}) → Löschen")
                    to_remove.append(neu)
                    break  # Stop bei erstem nahen GOOD_

        removed_count = 0
        for track in to_remove:
            try:
                print(f"🗑️ Lösche Track: {track.name}")
                tracks.remove(track)
                removed_count += 1
            except Exception as e:
                print(f"❌ Fehler beim Löschen von {track.name}: {e}")

        self.report({'INFO'}, f"🗑️ Gelöscht: {removed_count} NEU_-Marker im Frame {current_frame}")
        return {'FINISHED'}


class CLIP_PT_neu_cleanup_tools(bpy.types.Panel):
    bl_label = "NEU_-Cleanup"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tools'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.remove_close_neu_markers")


def register():
    bpy.utils.register_class(CLIP_OT_remove_close_neu_markers)
    bpy.utils.register_class(CLIP_PT_neu_cleanup_tools)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_remove_close_neu_markers)
    bpy.utils.unregister_class(CLIP_PT_neu_cleanup_tools)


if __name__ == "__main__":
    register()