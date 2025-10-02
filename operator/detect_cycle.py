import bpy
from bpy.types import Operator

from ..helpers.bootstrap import bootstrap
from ..helpers.snapshot import snapshot
from ..helpers.detect import detect_features
from ..helpers.newmarker import newmarker
from ..helpers.cleanup import cleanup
from ..helpers.control import control_cycle


class KAISERLICH_OT_detect_cyclus(Operator):
    bl_idname = "clip.kaiserlich_detect_cyclus"
    bl_label = "Kaiserlich Detect Cyclus"
    bl_description = "Starte den automatischen Marker-Detektions-Cyclus"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            self.detect_cyclus(context)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and getattr(space, 'clip', None) is not None

    # Rekursiver Zyklus entsprechend Pseudocode
    def detect_cyclus(self, context, values=None):
        if values is None:
            values = bootstrap(context)
        # Tiefe absichern
        depth = values.setdefault('_depth', 0)
        if depth > 12:
            print('[Kaiserlich] Abbruch: Maximale Rekursion erreicht')
            return
        values['_depth'] = depth + 1

        # Snapshot alte Marker
        lm = snapshot(context)
        # Neue Features erkennen
        detect_features(context, values)
        # Neue Marker einsammeln
        nm = newmarker(context)
        # Cleanup gegen alte Marker
        cleanup(context, nm, lm, values)
        # Kontrolle & ggf. Restart
        restart = control_cycle(context, nm, values, restart_callback=lambda: self.detect_cyclus(context, values))
        if not restart:
            print('[Kaiserlich] Cyclus finished in depth', depth)
