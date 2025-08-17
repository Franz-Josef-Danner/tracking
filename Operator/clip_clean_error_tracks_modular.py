# file: Operators/clip_clean_error_tracks_modular.py
import bpy
from ..Helper.clean_error_tracks import run_clean_error_tracks

class CLIP_OT_clean_error_tracks_modular(bpy.types.Operator):
    """Clean Error Tracks (modular, mit UI‑Fortschritt)"""
    bl_idname = "clip.clean_error_tracks_modular"
    bl_label = "Clean Error Tracks (Modular UI)"
    bl_options = {'REGISTER', 'UNDO'}

    _progress = 0.0

    def _notify(self, step, msg, progress):
        wm = bpy.context.window_manager
        # Fortschritt
        if progress is not None:
            self._progress = max(0.0, min(1.0, float(progress)))
            wm.progress_update(int(self._progress * 100))

        # Statuszeile (Header)
        try:
            win = bpy.context.window
            if win and win.screen and win.screen.areas:
                for area in win.screen.areas:
                    if area.type == 'STATUSBAR':
                        area.tag_redraw()
                        break
        except Exception:
            pass

        # Kurze Meldungen auch als Info
        if msg:
            bpy.context.workspace.status_text_set(f"[{step}] {msg}")

        # Sofortiger UI‑Refresh (reduziert „Block‑Gefühl“)
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
        except Exception:
            pass

    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 100)
        bpy.context.workspace.status_text_set("Clean Error Tracks startet …")

        try:
            result = run_clean_error_tracks(context, notify=self._notify, do_ui_report=False)
        finally:
            wm.progress_end()
            bpy.context.workspace.status_text_set(None)

        # finaler Report
        if result.get('CANCELLED'):
            self.report({'ERROR'}, "Clean Error Tracks abgebrochen.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Clean Error Tracks abgeschlossen.")
        return {'FINISHED'}


# Registration helper
def register():
    bpy.utils.register_class(CLIP_OT_clean_error_tracks_modular)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_clean_error_tracks_modular)
