import bpy
from .strm_utils import (
    extract_grayscale_frames,
    analyze_strm,
    compute_tile_coords,
    select_top_tiles_as_rois,
    extract_single_grayscale_frame,
    detect_features_in_roi,
)
from .strm_overlay import draw_tile_overlay_callback, get_overlay_state


class STRM_OT_Analyze(bpy.types.Operator):
    bl_idname = "clip.strm_analyze"
    bl_label = "STRM Analyse"
    bl_description = "Analysiert das Video in Tiles und berechnet Texture/Motion Scores"

    def execute(self, context):
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        try:
            frames = extract_grayscale_frames(clip, start=0, count=10)
        except Exception as e:
            self.report({'ERROR'}, f"Fehler beim Lesen der Frames: {e}")
            return {'CANCELLED'}

        if not frames:
            self.report({'ERROR'}, "Fehler beim Lesen der Frames.")
            return {'CANCELLED'}

        try:
            tile_data = analyze_strm(frames, tile_rows=4, tile_cols=6)
        except Exception as e:
            self.report({'ERROR'}, f"Fehler bei STRM-Analyse: {e}")
            return {'CANCELLED'}

        # Ergebnisse in Szene speichern (für Overlay)
        overlay = get_overlay_state(context.scene)
        overlay["tiles"] = tile_data
        overlay["enabled"] = True
        overlay["score_type"] = overlay.get("score_type", "motion")

        print("\n[STRM-Ausgabe]")
        for idx, t in enumerate(tile_data):
            print(
                f"Tile {idx} (r{t['tile'][0]}c{t['tile'][1]}): "
                f"Texture={t['texture']:.3f}, Motion={t['motion']:.3f}, "
                f"Divergence={t['div']:.3f}, Flicker={t['flicker']:.3f}"
            )

        self.report({'INFO'}, f"{len(tile_data)} Tiles analysiert.")
        return {'FINISHED'}


_draw_handle = None


class STRM_OT_ToggleOverlay(bpy.types.Operator):
    bl_idname = "clip.strm_toggle_overlay"
    bl_label = "Toggle STRM Overlay"
    bl_description = "Zeigt/versteckt das STRM Tile-Gitter"

    tile_rows = bpy.props.IntProperty(name="Rows", default=4, min=1, max=64)
    tile_cols = bpy.props.IntProperty(name="Cols", default=6, min=1, max=64)

    def execute(self, context):
        global _draw_handle

        scene = context.scene
        overlay = get_overlay_state(scene)
        enabled = not overlay.get("enabled", False)
        overlay["enabled"] = enabled

        if enabled:
            clip = context.edit_movieclip
            if not clip:
                self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
                overlay["enabled"] = False
                return {'CANCELLED'}

            overlay["tiles"] = compute_tile_coords(clip, self.tile_rows, self.tile_cols)

            if _draw_handle is None:
                _draw_handle = bpy.types.SpaceClipEditor.draw_handler_add(
                    draw_tile_overlay_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        else:
            if _draw_handle is not None:
                bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
                _draw_handle = None

        # Region neu zeichnen
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()
        return {'FINISHED'}


class STRM_OT_SetOverlayScore(bpy.types.Operator):
    bl_idname = "clip.strm_set_overlay_score"
    bl_label = "Set STRM Overlay Score"
    bl_description = "Wählt den Score-Typ für das farbige Overlay"

    items = [
        ('motion', "Motion", "Bewegung"),
        ('texture', "Texture", "Textur"),
        ('div', "Divergence", "Divergenz"),
        ('flicker', "Flicker", "Helligkeitsschwankung"),
    ]
    score_type = bpy.props.EnumProperty(name="Score", items=items, default='motion')

    def execute(self, context):
        overlay = get_overlay_state(context.scene)
        overlay["score_type"] = self.score_type

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()
        return {'FINISHED'}


class STRM_OT_SelectROIs(bpy.types.Operator):
    bl_idname = "clip.strm_select_rois"
    bl_label = "STRM: Select ROIs"
    bl_description = "Wählt Top-N STRM-Tiles als ROIs basierend auf Score"

    top_n = bpy.props.IntProperty(name="Top N", default=6, min=1, max=100)
    score_type = bpy.props.EnumProperty(
        name="Score Type",
        items=[
            ("motion", "Motion", ""),
            ("texture", "Texture", ""),
            ("div", "Divergence", ""),
            ("flicker", "Flicker", ""),
        ],
        default="motion",
    )

    def execute(self, context):
        overlay = get_overlay_state(context.scene)
        tiles = overlay.get("tiles", [])
        if not tiles:
            self.report({'ERROR'}, "Keine STRM-Tiles gefunden.")
            return {'CANCELLED'}

        rois = select_top_tiles_as_rois(
            tiles,
            score_type=self.score_type,
            top_n=self.top_n,
            min_distance_px=20,
        )

        overlay["rois"] = rois
        overlay["score_type"] = self.score_type

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{len(rois)} ROIs gewählt (nach {self.score_type})")
        return {'FINISHED'}


class STRM_OT_SeedFeatures(bpy.types.Operator):
    bl_idname = "clip.strm_seed_features"
    bl_label = "STRM: Seed Features"
    bl_description = "Seede Keypoints in den ausgewählten ROIs"

    max_features_per_roi = bpy.props.IntProperty(name="Max/ROI", default=50, min=1, max=500)
    quality_level = bpy.props.FloatProperty(name="Quality", default=0.01, min=0.0001, max=0.1)
    min_distance = bpy.props.IntProperty(name="Min Dist", default=5, min=1, max=50)

    def execute(self, context):
        scene = context.scene
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        overlay = get_overlay_state(scene)
        rois = overlay.get("rois", [])
        if not rois:
            self.report({'ERROR'}, "Keine ROIs zum Seeden.")
            return {'CANCELLED'}

        frame_num = scene.frame_current
        gray = extract_single_grayscale_frame(clip, frame_num)
        if gray is None:
            self.report({'ERROR'}, "Frame konnte nicht gelesen werden.")
            return {'CANCELLED'}

        all_points = []
        try:
            for roi in rois:
                pts = detect_features_in_roi(
                    gray,
                    roi,
                    max_features=self.max_features_per_roi,
                    quality=self.quality_level,
                    min_distance=self.min_distance,
                )
                all_points.extend(pts)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        overlay["markers"] = all_points

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{len(all_points)} Features gesät.")
        return {'FINISHED'}


def cleanup_overlay_draw():
    """Remove draw handler if active (called on addon unregister)."""
    global _draw_handle
    if _draw_handle is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
        except Exception:
            pass
        _draw_handle = None
