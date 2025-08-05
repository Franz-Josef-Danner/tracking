import bpy
from ..Helper.select_short_tracks import select_short_tracks
from ..Helper.delete_selected_markers import delete_selected_markers

class CLIP_OT_delete_short_tracks(bpy.types.Operator):
    bl_idname = "clip.select_and_delete_short_tracks"
    bl_label = "Kurze Tracks selektieren & löschen"
    bl_description = "Selektiert zu kurze Tracks und löscht deren Marker"

    min_track_length: bpy.props.IntProperty(
        name="Minimale Tracking-Länge",
        default=10,
        min=1,
        description="Tracks mit weniger Markern werden gelöscht"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein aktiver Movie Clip.")
            return {'CANCELLED'}

        tracks = clip.tracking.tracks
        selected = select_short_tracks(tracks, self.min_track_length)
        delete_selected_markers(tracks)

        self.report({'INFO'}, f"{selected} Tracks selektiert und Marker gelöscht.")
        return {'FINISHED'}
