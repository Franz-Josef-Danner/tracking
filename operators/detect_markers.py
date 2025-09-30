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

    verbose = bpy.props.BoolProperty(
        name="Verbose",
        description="Ausführliche Debug-Ausgaben in der Konsole",
        default=False,
    )

    def execute(self, context):
        result = detect_features_multipass(context, verbose=self.verbose)
        if not result.get('success'):
            self.report({'ERROR'}, result.get('message', 'Unbekannter Fehler'))
            return {'CANCELLED'}

        passes = result.get('passes', 0)
        total_added = result.get('total_added', -1)
        per_pass = result.get('per_pass', [])

        summary_parts = []
        for thr, added, note in per_pass:
            base = f'{thr:.5f}:{added}'
            if note:
                base += f' ({note})'
            summary_parts.append(base)
        summary = ', '.join(summary_parts) if summary_parts else 'keine Marker hinzugefügt'

        self.report({'INFO'}, f'{passes} Durchläufe, hinzugefügt: {total_added} (pro Pass: {summary})')
        return {'FINISHED'}
