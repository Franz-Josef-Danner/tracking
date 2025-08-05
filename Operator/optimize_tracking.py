    def execute(self, context):
        # --- Initialwerte ---
        pt = 21
        sus = pt * 2
        threshold = 0.5
        ev = -1
        dg = 0
        ptv = pt
        mov = 0
        vf = 0

        # ⬅️ Helper-Operator ausführen
        def call_marker_helper():
            bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')

        # ⬅️ Marker setzen durch eigenen Operator
        def set_marker():
            call_marker_helper()
            bpy.ops.tracking.detect('INVOKE_DEFAULT')  # <- Dein "TRACKING_OT_detect"

        # ⬅️ Tracking über ganze Sequenz
        def track():
            clip = context.space_data.clip
            tracking = clip.tracking
            tracks = tracking.tracks
            fr_start = context.scene.frame_start
            fr_end = context.scene.frame_end

            for track in tracks:
                if track.select:
                    context.space_data.tracking.tracks.active = track
                    bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
                    print(f"[Tracking] '{track.name}' tracked from frame {fr_start} to {fr_end}")

        # Dummy-Funktionen
        def frames_per_track():
            return 20  # Ersetze mit echter Auswertung, z. B. Markeranzahl

        def measure_error():
            return 0.5  # Ersetze mit echter Fehlerauswertung, z. B. Track.average_error

        def sum_all(val):
            return val  # Erweitern: Summe über alle Marker-Werte

        def set_flag1():
            pass

        def set_flag2():
            pass

        def set_flag3():
            pass

        # --- Zyklus 1 ---
        for _ in range(10):
            set_flag1()
            set_marker()
            track()
            f_i = frames_per_track()
            e_i = measure_error()
            eg_i = f_i / e_i
            ega = sum_all(eg_i)

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

        # --- Zyklus 2 ---
        mo_index = 0
        while mo_index < 5:
            set_flag2()
            set_marker()
            track()
            f_i = frames_per_track()
            e_i = measure_error()
            eg_i = f_i / e_i
            ega = sum_all(eg_i)

            if ega > ev:
                ev = ega
                mov = mo_index
            mo_index += 1

        # Motion-Model zu RGB
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

        # --- Zyklus 3 ---
        vv = 0
        while vv < 4:
            set_flag3()
            set_marker()
            track()
            f_i = frames_per_track()
            e_i = measure_error()
            eg_i = f_i / e_i
            ega = sum_all(eg_i)

            if ega > ev:
                ev = ega
                vf = vv
            vv += 1

        R = (vf == 0 or vf == 1)
        G = (vf == 1 or vf == 2 or vf == 3)
        B = (vf == 3 or vf == 4)

        self.report({'INFO'}, f"Optimierung abgeschlossen: ev={ev:.2f}, Motion={mov}, RGB=({R},{G},{B})")
        return {'FINISHED'}
