import bpy


class STRM_PT_Panel(bpy.types.Panel):
    bl_label = "STRM Tracker"
    bl_idname = "CLIP_PT_strm_tracker"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'STRM'

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.strm_analyze", icon='VIEWZOOM')
        layout.operator("clip.strm_toggle_overlay", icon='GRID')
        row = layout.row(align=True)
        row.operator("clip.strm_set_overlay_score", text="Motion").score_type = 'motion'
        row.operator("clip.strm_set_overlay_score", text="Texture").score_type = 'texture'
        row = layout.row(align=True)
        row.operator("clip.strm_set_overlay_score", text="Divergence").score_type = 'div'
        row.operator("clip.strm_set_overlay_score", text="Flicker").score_type = 'flicker'
        layout.separator()
        layout.operator("clip.strm_select_rois", icon='SELECT_SET')
        layout.operator("clip.strm_seed_features", icon='PARTICLES')
        layout.operator("clip.strm_track_markers", icon='TRACKING')
        layout.operator("clip.strm_eval_kpis", icon='INFO')
        layout.operator("clip.strm_cleanup_tracks", icon='PANEL_CLOSE')
        layout.operator("clip.strm_fit_motion_model", icon='CONSTRAINT')
        layout.operator("clip.strm_cluster_fit_promote", icon='GROUP')
        layout.operator("clip.strm_promotion_step", icon='SORTSIZE')
        layout.operator("clip.strm_peer_snap_reseed", icon='SNAP_ON')
