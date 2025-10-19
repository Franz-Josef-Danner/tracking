from bpy.types import Operator
from ..Helper import snapshot, detect, track_helper

class AUTO_OT_Calibrate(Operator):
    bl_idname = "tracking.auto_calibrate"
    bl_label = "Auto Calibrate Tracking"

    def execute(self, context):
        # --- Snapshot vor Detect/Track ---
        baseline_tracks = snapshot.create_marker_snapshot(context)
        self.report({'INFO'}, f"{len(baseline_tracks)} Baseline-Marker erfasst.")

        # --- Detect/Track-Vorgang starten ---
        detect.run_detect_and_adapt(context)
        track_helper.run_tracking(context)

        # --- Neue Marker erkennen ---
        new_tracks = snapshot.compare_with_baseline(context, baseline_tracks)
        self.report({'INFO'}, f"{len(new_tracks)} neue Marker hinzugefügt.")

        return {'FINISHED'}
