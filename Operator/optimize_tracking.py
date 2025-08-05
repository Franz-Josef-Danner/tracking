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

        # Basiswerte
        pt = 21
        sus = pt * 2
        ev = -1
        dg = 0
        ptv = pt
        mov = 0
        vf = 0

        # Zielwerte setzen
        set_test_value(context)
        self.report({'INFO'}, "Pattern/Search-Size gesetzt.")

        # ----- Helper-Funktionen -----
        def set_flag1_for_all(pattern, search):
            for track in clip.tracking.tracks:
                if track.select:
                    track.settings.pattern_size = pattern
                    track.settings.search_size = search

        def set_flag2(index):
            motion_models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot']
            if 0 <= index < len(motion_models):
                clip.tracking.settings.motion_model = motion_models[index]
            else:
                print(f"[WARNUNG] Ungültiger motion_model-Index: {index}")

        def set_flag3(index):
            s = clip.tracking.settings
            s.use_red_channel = (index in [0, 1])
            s.use_green_channel = (index in [1, 2, 3])
            s.use_blue_channel = (index in [3, 4])

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
                    clip.tracking.tracks.active = t
                    bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)

        def frames_per_track_all():
            return sum(len(t.markers) for t in clip.tracking.tracks if t.select)

        def measure_error_all():
            return error_value(clip)

        def eg(frames, error):
            return frames / error if error else 0

        # ----- Zyklus 1: Pattern / Search Size -----

        for _ in range(10):
            set_flag1_for_all(pt, sus)
            set_marker()
            track()
            f = frames_per_track_all()
            e = measure_error_all()
            g = eg(f, e)
            e = e or 0.0
            g = g or 0.0
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

        # ----- Zyklus 2: Motion Model -----

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

        # ----- Zyklus 3: Farbkanäle -----

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

        # Final setzen
        set_flag2(mov)
        set_flag3(vf)

        print(f"[FINAL] ev={ev:.4f}, Motion={mov}, RGB={vf}")
        self.report({'INFO'}, f"Fertig: ev={ev:.2f}, Motion={mov}, RGB={vf}")
        return {'FINISHED'}
