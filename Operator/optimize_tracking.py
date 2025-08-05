import bpy
from Helper.set_test_value import set_test_value
from Helper.error_value import calculate_clip_error
from Operator.detect import perform_marker_detection


class TRACK_OT_optimize_tracking(bpy.types.Operator):
    bl_idname = "tracking.optimize_tracking"
    bl_label = "Optimiertes Tracking durchführen"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        print("[START] Optimierung gestartet")

        # Vorbedingung prüfen
        clip = context.space_data.clip
        if not clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        # 1. Initialwerte
        pt = 21
        sus = pt * 2
        threshold = 0.5
        ev = -1
        dg = 0
        ptv = pt
        mov = 0
        vf = 0

        set_test_value(context)
        self.report({'INFO'}, "Pattern/Search-Size gesetzt.")

        # --- Helper-Funktionen ---

        def set_flag1(pattern, search):
            print(f"[set_flag1] Setting pattern={pattern}, search={search}")
            for track in clip.tracking.tracks:
                if track.select:
                    track.pattern_size = (pattern, pattern)
                    track.search_size = (search, search)

        def set_flag2(index):
            motion_models = [
                'Perspective',
                'Affine',
                'LocRotScale',
                'LocScale',
                'LocRot'
            ]
            tracking_settings = clip.tracking.settings
            tracking_settings.motion_model = motion_models[index]
            print(f"[set_flag2] Motion Model = {motion_models[index]}")

        def set_flag3(vf_index):
            settings = clip.tracking.settings
            R = (vf_index == 0 or vf_index == 1)
            G = (vf_index == 1 or vf_index == 2 or vf_index == 3)
            B = (vf_index == 3 or vf_index == 4)
            settings.use_red_channel = R
            settings.use_green_channel = G
            settings.use_blue_channel = B
            print(f"[set_flag3] RGB: R={R}, G={G}, B={B}")

        def call_marker_helper():
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        def set_marker():
            call_marker_helper()
            threshold = 0.75
            image_width = clip.size[0]
            margin_base = int(image_width * 0.025)
            min_distance_base = int(image_width * 0.05)
            count = perform_marker_detection(
                clip=clip,
                tracking=clip.tracking,
                threshold=threshold,
                margin=margin_base,
                min_distance=min_distance_base
            )
            print(f"[set_marker] {count} Marker gesetzt.")

        def track():
            frame_start = context.scene.frame_start
            frame_end = context.scene.frame_end
            for track in clip.tracking.tracks:
                if track.select:
                    context.space_data.tracking.tracks.active = track
                    bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=True)
                    print(f"[track] '{track.name}' getrackt von Frame {frame_start} bis {frame_end}")

        def frames_per_track_all():
            return sum(len(track.markers) for track in clip.tracking.tracks if track.select)

        def measure_error_all():
            return calculate_clip_error(clip)

        def eg_value(frames, error):
            return frames / error if error != 0 else 0

        # --- Zyklus 1: Pattern-/Search-Size Optimierung ---
        for _ in range(10):
            set_flag1(pt, sus)
            set_marker()
            track()

            f_i = frames_per_track_all()
            e_i = measure_error_all()
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

            print(f"[Zyklus 1] f_i={f_i}, e_i={e_i:.6f}, eg_i={eg_i:.4f}")

            if ev < 0:
                ev = ega
                pt *= 1.1
                sus = pt * 2
            elif ega > ev:
                ev = ega
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

        # --- Zyklus 2: Motion-Model Optimierung ---
        mo_index = 0
        while mo_index < 5:
            set_flag2(mo_index)
            set_marker()
            track()

            f_i = frames_per_track_all()
            e_i = measure_error_all()
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

            print(f"[Zyklus 2] Motion {mo_index} → eg_i={eg_i:.4f}")

            if ega > ev:
                ev = ega
                mov = mo_index

            mo_index += 1

        # --- Zyklus 3: RGB-Kanal Optimierung ---
        vv = 0
        while vv < 5:
            set_flag3(vv)
            set_marker()
            track()

            f_i = frames_per_track_all()
            e_i = measure_error_all()
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

            print(f"[Zyklus 3] Kanal {vv} → eg_i={eg_i:.4f}")

            if ega > ev:
                ev = ega
                vf = vv

            vv += 1

        # Finales RGB-Set
        set_flag3(vf)

        print(f"[FINAL] ev={ev:.4f}, Motion={mov}, RGB-Auswahl={vf}")
        self.report({'INFO'}, f"Optimierung abgeschlossen: ev={ev:.2f}, Motion={mov}, RGB={vf}")
        return {'FINISHED'}


# Registrierung
def register():
    bpy.utils.register_class(TRACK_OT_optimize_tracking)

def unregister():
    bpy.utils.unregister_class(TRACK_OT_optimize_tracking)

if __name__ == "__main__":
    register()
    bpy.ops.tracking.optimize_tracking()
