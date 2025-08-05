import bpy
from bpy.types import Operator
from ..Helper.set_test_value import set_test_value
from ..Helper.error_value import error_value
from .detect import perform_marker_detection

class CLIP_OT_optimize_tracking(bpy.types.Operator):
    bl_idname = "clip.optimize_tracking"
    bl_label = "Optimiertes Tracking durchführen"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        print("[START] Optimierung gestartet")

        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        pt = 21
        sus = pt * 2
        ev = -1
        dg = 0
        ptv = pt
        mov = 0
        vf = 0

        set_test_value(context)
        self.report({'INFO'}, "Pattern/Search-Size gesetzt.")

        def set_flag1(track, pattern, search):
            track.settings.pattern_size = pattern
            track.settings.search_size = search


        def set_flag2(index):
            motion_models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot']
            clip.tracking.settings.motion_model = motion_models[index]

        def set_flag3(vf_index):
            s = clip.tracking.settings
            s.use_red_channel = (vf_index == 0 or vf_index == 1)
            s.use_green_channel = (vf_index == 1 or vf_index == 2 or vf_index == 3)
            s.use_blue_channel = (vf_index == 3 or vf_index == 4)

        def call_marker_helper():
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        def set_marker():
            call_marker_helper()
            w = clip.size[0]
            margin = int(w * 0.025)
            min_dist = int(w * 0.05)
            count = perform_marker_detection(clip, clip.tracking, 0.75, margin, min_dist)
            print(f"[set_marker] {count} Marker gesetzt.")

        def track():
            for t in clip.tracking.tracks:
                if t.select:
                    context.space_data.clip.tracking.tracks.active = t
                    bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)

        def frames_per_track_all():
            return sum(len(t.markers) for t in clip.tracking.tracks if t.select)

        def measure_error_all():
            error = error_value(context.scene)

        def eg(frames, error):
            return frames / error if error else 0

        # Zyklus 1
        for _ in range(10):
            set_flag1(pt, sus)
            set_marker()
            track()
            f = frames_per_track_all()
            e = measure_error_all()
            g = eg(f, e)
            e = e if e is not None else 0.0
            g = g if g is not None else 0.0 
            print(f"[Zyklus 1] f={f}, e={e:.4f}, g={g:.4f}")
            if ev < 0:
                ev = g
                pt *= 1.1
                sus = pt * 2
            elif g > ev:
                ev = g
                dg = 4
                ptv = pt
                pt *= 1.1
                sus = pt * 2
            else:
                dg -= 1
                if dg >= 0:
                    pt *= 1.1
                    sus = pt * 2
                else:
                    pt = ptv
                    sus = pt * 2
                    break

        # Zyklus 2
        for mo in range(5):
            set_flag2(mo)
            set_marker()
            track()
            f = frames_per_track_all()
            e = measure_error_all()
            g = eg(f, e)
            print(f"[Zyklus 2] Motion {mo} → g={g:.4f}")
            if g > ev:
                ev = g
                mov = mo

        # Zyklus 3
        for i in range(5):
            set_flag3(i)
            set_marker()
            track()
            f = frames_per_track_all()
            e = measure_error_all()
            g = eg(f, e)
            print(f"[Zyklus 3] RGB {i} → g={g:.4f}")
            if g > ev:
                ev = g
                vf = i

        set_flag3(vf)
        print(f"[FINAL] ev={ev:.4f}, Motion={mov}, RGB={vf}")
        self.report({'INFO'}, f"Fertig: ev={ev:.2f}, Motion={mov}, RGB={vf}")
        return {'FINISHED'}
