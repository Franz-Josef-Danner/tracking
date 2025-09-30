import bpy
from ..helpers.detect_helper import detect_features_multipass


class TRACKING_OT_detect_markers(bpy.types.Operator):
    bl_idname = "tracking.detect_markers"
    bl_label = "Detect Markers"
    bl_description = (
        "Mehrfaches Feature-Detect: Startet bei Threshold=1.0 und halbiert bis < 0.0001.\n"
        "So werden erst sehr starke, dann zunehmend schwächere Features hinzugefügt."
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        result = detect_features_multipass(context)
        if not result.get('success'):
            self.report({'ERROR'}, result.get('message', 'Unbekannter Fehler'))
            return {'CANCELLED'}
        passes = result.get('passes', 0)
        total_added = result.get('total_added', -1)
        total_removed = result.get('total_removed', 0)
        per_pass = result.get('per_pass', [])

        summary_parts = []
        for thr, added, removed, note in per_pass:
            base = f'{thr:.5f}: +{added} -{removed}'
            if note:
                base += f' ({note.strip()})'
            summary_parts.append(base)
        summary = ', '.join(summary_parts) if summary_parts else 'keine Marker hinzugefügt'

        self.report({'INFO'}, f'{passes} Durchläufe, netto hinzugefügt: {total_added}, entfernt (Duplikate): {total_removed} (Details: {summary})')
        return {'FINISHED'}
