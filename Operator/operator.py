import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import diff_markers, classify_markers
from ..Helper.cleaneup import cleanup_new_markers

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

        # 4. Klassifikation (alte vs neue Marker)
        alte_marker, neue_marker = classify_markers(before, after)

        # 5. Cleanup: Neue Marker verwerfen, die zu nah an alten liegen
        cleaned_new, deleted = cleanup_new_markers(
            context,
            alte_marker,
            neue_marker,
            md=params['md'],
            hz=params['hz'],
            vc=params['vc']
        )

        # Für Kompatibilität weiterhin diff bereitstellen (nur neue vor Cleanup)
        _ = diff_markers(before, after)  # Logging (zeigt rohe neuen Marker)

        self.report({'INFO'}, (
            f"Detect fertig: geschätzt ~{created} neue Tracks | Vor Cleanup: {len(neue_marker)} | Entfernt: {deleted} | "
            f"Behaltene neue: {len(cleaned_new)} | Vorher {len(before)} -> Nachher {len(after)} (alte behalten: {len(alte_marker)})"
        ))
        return {'FINISHED'}
