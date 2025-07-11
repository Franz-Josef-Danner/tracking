"""Cleanup NEW_ markers that are too close to GOOD_ markers.

This script is intended for manual use in Blender's text editor. It registers
an operator that deletes NEW_ markers in the current frame when they are closer
than a configurable distance to existing GOOD_ markers.
"""

import bpy
import mathutils

bl_info = {
    "name": "NEW_ Marker Cleanup",
    "description": (
        "Entfernt NEW_-Marker, die im aktuellen Frame zu nah an GOOD_-Markern liegen"
    ),
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
}

class CLIP_OT_remove_close_new_markers(bpy.types.Operator):
    bl_idname = "clip.remove_close_new_markers"
    bl_label = "NEW_-Marker löschen (zu nahe an GOOD_)"
    bl_description = (
        "Löscht NEW_-Marker im aktuellen Frame, wenn sie zu nahe an GOOD_-Markern liegen"
    )

    bl_options = {"REGISTER", "UNDO"}

    min_distance: bpy.props.FloatProperty(
        name="Mindestabstand",
        default=0.02,
        description="Mindestabstand im normierten Raum (0-1) zum Löschen",
        min=0.0,
    )

    @classmethod
    def poll(cls, context):
        return (
            context.space_data
            and context.space_data.type == 'CLIP_EDITOR'
            and context.space_data.clip
        )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "❌ Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        current_frame = context.scene.frame_current
        tracks = clip.tracking.tracks

        # Listen vorbereiten
        neu_tracks = [t for t in tracks if t.name.startswith("NEW_")]
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
                    msg = (
                        f"⚠️ {neu.name} ist zu nahe an {good.name} (Distanz: {distance:.5f}) → Löschen"
                    )
                    self.report({'INFO'}, msg)
                    to_remove.append(neu)
                    break  # Stop bei erstem nahen GOOD_

        if not to_remove:
            self.report({'INFO'}, "Keine NEW_-Marker zum Löschen gefunden")
            return {'CANCELLED'}

        # Tracks markieren
        for t in tracks:
            t.select = False
        for t in to_remove:
            t.select = True

        # Operator im Clip Editor ausführen
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                with context.temp_override(
                                    area=area,
                                    region=region,
                                    space_data=space,
                                ):
                                    bpy.ops.clip.delete_track()
                                self.report(
                                    {'INFO'},
                                    f"🗑️ Gelöscht: {len(to_remove)} NEW_-Marker im Frame {current_frame}",
                                )
                                return {'FINISHED'}

        self.report({'ERROR'}, "Kein geeigneter Clip Editor Bereich gefunden")
        return {'CANCELLED'}


class CLIP_PT_new_cleanup_tools(bpy.types.Panel):
    bl_label = "NEW_-Cleanup"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tools'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.window_manager, "cleanup_min_distance")
        op = layout.operator(CLIP_OT_remove_close_new_markers.bl_idname)
        op.min_distance = context.window_manager.cleanup_min_distance


def register():
    bpy.utils.register_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.register_class(CLIP_PT_new_cleanup_tools)
    if not hasattr(bpy.types.WindowManager, "cleanup_min_distance"):
        bpy.types.WindowManager.cleanup_min_distance = bpy.props.FloatProperty(
            name="Mindestabstand",
            default=0.02,
            description="Mindestabstand im normierten Raum (0-1) zum Löschen",
            min=0.0,
        )


def unregister():
    if hasattr(bpy.types.WindowManager, "cleanup_min_distance"):
        del bpy.types.WindowManager.cleanup_min_distance
    bpy.utils.unregister_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.unregister_class(CLIP_PT_new_cleanup_tools)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
