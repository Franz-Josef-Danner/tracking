import bpy
from .strm_utils import extract_grayscale_frames, analyze_strm


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
