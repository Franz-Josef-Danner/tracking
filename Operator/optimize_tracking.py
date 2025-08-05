import bpy
from set_test_value import set_test_value  # muss im Add-on-Ordner liegen
from error_value import calculate_clip_error  # muss in Helper/error_value.py liegen


class TRACK_OT_optimize_tracking(bpy.types.Operator):
    bl_idname = "tracking.optimize_tracking"
    bl_label = "Optimiertes Tracking durchführen"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1️⃣ Pattern/Search-Size setzen
        set_test_value(context)
        self.report({'INFO'}, "Pattern/Search-Size gesetzt.")

        # 2️⃣ Marker-Helfer starten
        def call_marker_helper():
            bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')

        # 3️⃣ Marker setzen durch externen Detect-Operator
        def set_marker():
            call_marker_helper()
            bpy.ops.tracking.detect('INVOKE_DEFAULT')

        # 4️⃣ Tracking ausführen
        def track():
            clip = context.space_data.clip
            tracks = clip.tracking.tracks
            frame_start = context.scene.frame_start
            frame_end = context.scene.frame_end

            for track in tracks:
                if track.select:
                    context.space_data.tracking.tracks.active = track
                    bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
                    print(f"[Tracking] Track '{track.name}' von Frame {frame_start} bis {frame_end}")

        # 🔢 Anzahl Marker über Frames
        def frames_per_track_all(context):
            clip = context.space_data.clip
            return sum(len(track.markers) for track in clip.tracking.tracks if track.select)

        # 📏 Fehler über Standardabweichung
        def measure_error_all(context):
            clip = context.space_data.clip
            if not clip:
                return 1.0
            return calculate_clip_error(clip)

        # 📊 Effizienz berechnen
        def eg_value(frames, error):
            return frames / error if error != 0 else 0

        # --- Flags als Platzhalter ---
        def set_flag1():
            def set_flag1():
                clip = bpy.context.space_data.clip
                tracks = clip.tracking.tracks
            
                pattern_size = pt  # globaler Wert aus deinem Optimierungsloop
                search_size = sus
            
                for track in tracks:
                    if track.select:
                        track.pattern_size = (pattern_size, pattern_size)
                        track.search_size = (search_size, search_size)
                        print(f"[set_flag1] {track.name} pattern={pattern_size}, search={search_size}")


        def set_flag2():
            def set_flag2():
                clip_editor = bpy.context.space_data
                tracking_settings = clip_editor.clip.tracking.settings
            
                motion_models = [
                    'Perspective',
                    'Affine',
                    'LocRotScale',
                    'LocScale',
                    'LocRot'
                ]

                index = mo_index  # dein aktueller Motion-Index aus der Optimierung
                print(f"[DEBUG] set_flag2 → Motion Model Index: {index}")  # <-- HIER
                tracking_settings.motion_model = motion_models[index]
                print(f"[set_flag2] motion_model set to {motion_models[index]}")


        def set_flag3():
            def set_flag3():
            clip_editor = bpy.context.space_data
            tracking_settings = clip_editor.clip.tracking.settings
        
            vf_index = vf  # dein RGB-Auswahl-Index aus der Optimierung
        
            if vf_index == 0:
                R, G, B = True, False, False
            elif vf_index == 1:
                R, G, B = True, True, False
            elif vf_index == 2:
                R, G, B = False, True, False
            elif vf_index == 3:
                R, G, B = False, True, True
            elif vf_index == 4:
                R, G, B = False, False, True
        
            tracking_settings.use_red_channel = R
            tracking_settings.use_green_channel = G
            tracking_settings.use_blue_channel = B
        
            print(f"[set_flag3] RGB set to R={R}, G={G}, B={B}")


        # 🔁 Zyklus 1: Pattern-/Search-Size Optimierung
        pt = 21
        sus = pt * 2
        threshold = 0.5
        ev = -1
        dg = 0
        ptv = pt
        mov = 0
        vf = 0

        for _ in range(10):
            set_flag1(pt, sus)()
            set_marker()
            track()
            f_i = frames_per_track_all(context)
            e_i = measure_error_all(context)
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

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

        # 🔁 Zyklus 2: Motion-Model Optimierung
        mo_index = 0
        while mo_index < 5:
            set_flag2()
            set_marker()
            track()
            f_i = frames_per_track_all(context)
            e_i = measure_error_all(context)
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

            if ega > ev:
                ev = ega
                mov = mo_index

            mo_index += 1

        # 🎨 RGB-Zuordnung nach Motion-Model
        if mov == 0:
            R, G, B = True, False, False
        elif mov == 1:
            R, G, B = True, True, False
        elif mov == 2:
            R, G, B = False, True, False
        elif mov == 3:
            R, G, B = False, True, True
        elif mov == 4:
            R, G, B = False, False, True

        # 🔁 Zyklus 3: RGB-Kanal-Optimierung
        vv = 0
        while vv < 4:
            set_flag3()
            set_marker()
            track()
            f_i = frames_per_track_all(context)
            e_i = measure_error_all(context)
            eg_i = eg_value(f_i, e_i)
            ega = eg_i

            if ega > ev:
                ev = ega
                vf = vv

            vv += 1

        # 🎯 Finales RGB-Ergebnis
        R = (vf == 0 or vf == 1)
        G = (vf == 1 or vf == 2 or vf == 3)
        B = (vf == 3 or vf == 4)

        self.report({'INFO'}, f"Optimierung abgeschlossen: ev={ev:.2f}, Motion={mov}, RGB=({R},{G},{B})")
        return {'FINISHED'}


# 📦 Registrierung
def register():
    bpy.utils.register_class(TRACK_OT_optimize_tracking)

def unregister():
    bpy.utils.unregister_class(TRACK_OT_optimize_tracking)

if __name__ == "__main__":
    register()
    bpy.ops.tracking.optimize_tracking()
