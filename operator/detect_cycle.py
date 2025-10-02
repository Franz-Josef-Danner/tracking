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

    # Iterativer Zyklus (statt Rekursion, um Überlauf zu vermeiden)
    def detect_cyclus(self, context, values=None):
        if values is None:
            values = bootstrap(context)

        max_loops = 15
        loop = 0
        while loop < max_loops:
            loop += 1
            values['_loop'] = loop
            # Snapshot alte Marker (alle aktiven am Frame)
            lm = snapshot(context)
            # Detect
            detect_features(context, values)
            # Neue Marker (roh)
            nm = newmarker(context)
            # Cleanup -> verbleibende neue Marker
            nm_clean = cleanup(context, nm, lm, values)
            # Kontrolle
            action = control_cycle(context, nm_clean, values)
            if action == 'done':
                print(f'[Kaiserlich] Cyclus finished in loop {loop}')
                break
            # 'retry' oder 'repeat' => Schleife fortsetzen
        else:
            print('[Kaiserlich] Abbruch: max_loops erreicht')
