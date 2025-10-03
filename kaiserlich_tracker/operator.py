import bpy
from bpy.types import Operator
from .helpers import bootstrap, snapshot, detect_features, newmarker, cleanup, control_cycle


class CLIP_OT_KaiserlichDetectCycle(Operator):
    bl_idname = "clip.kaiserlich_detect_cycle"
    bl_label = "Detect Cycle"
    bl_description = "Starte adaptiven Marker-Detection-Zyklus (max. 10 Iterationen)"
    bl_options = {'REGISTER', 'UNDO'}

    max_cycles: bpy.props.IntProperty(
        name="Max Zyklen",
        default=10,
        min=1,
        max=100
    )

    def execute(self, context):
        scene = context.scene

        if scene.kaiserlich_cycle_running:
            self.report({'WARNING'}, "Zyklus läuft bereits")
            return {'CANCELLED'}

        clip = context.edit_movieclip
        if clip is None:
            self.report({'ERROR'}, "Kein Movie Clip aktiv")
            return {'CANCELLED'}

        scene.kaiserlich_cycle_running = True
        try:
            detect_cycle(context, self.max_cycles, operator=self)
        finally:
            scene.kaiserlich_cycle_running = False

        return {'FINISHED'}


def detect_cycle(context, max_cycles=10, operator: Operator | None = None):
    """Kontrollschleife für adaptives Feature-Tracking.
    Passt threshold / min_distance / pattern_size an bis Zielbereich erreicht ist.
    """
    values = bootstrap(context)
    scene = context.scene

    for cycle in range(1, max_cycles + 1):
        old_markers = snapshot(context)
        detect_features(context, values)          # neue Marker detektieren
        new_markers = newmarker(context)
        cleanup(context, new_markers, old_markers, values)

        # Filter: Liste nach Cleanup neu ziehen (Marker könnten gelöscht worden sein)
        new_markers = [m for m in newmarker(context) if m not in old_markers]

        if control_cycle(context, new_markers, values):
            scene.kaiserlich_last_marker_count = len(new_markers)
            _log(operator, f"Erfolg nach {cycle} Zyklen: {len(new_markers)} Marker")
            break
    else:
        _log(operator, "Maximale Zykluszahl erreicht (Abbruch)")


def _log(operator: Operator | None, message: str):
    if operator:
        operator.report({'INFO'}, message)
    print(f"[Kaiserlich] {message}")
