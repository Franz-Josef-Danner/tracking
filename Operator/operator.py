import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import diff_markers

class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Zyklus"
    bl_description = "Bootstrap -> Snapshot -> Detect -> Snapshot -> Diff"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame

        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        # 1. Snapshot vorher
        before = snapshot_active_markers(context)

        # 2. Detect mit aus Bootstrap abgeleiteten Werten (tr, md, ma)
        created = detect_features(
            context,
            placement='FRAME',
            margin=int(params['ma']),
            threshold=float(params['tr']),
            min_distance=int(params['md'])
        )

        # 3. Snapshot nachher
        after = snapshot_active_markers(context)

        # 4. Diff
        new_markers = diff_markers(before, after)

        self.report({'INFO'}, f"Detect fertig: ~{created} neu, tatsächlich {len(new_markers)} neue aktive Marker")
        return {'FINISHED'}
