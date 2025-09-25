import bpy
from .strm_utils import extract_grayscale_frames, analyze_strm, compute_tile_coords
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


def cleanup_overlay_draw():
    """Remove draw handler if active (called on addon unregister)."""
    global _draw_handle
    if _draw_handle is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
        except Exception:
            pass
        _draw_handle = None
