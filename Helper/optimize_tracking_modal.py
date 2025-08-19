def run_step(self, context):
    """
    Ablauf gemäß Spezifikation:
      Defaults setzen → Detect → Track → Score (ega) → Vergleich/Update ev → Korridor (dg)
      → bei Abbruch Korridor: Motion-Model-Schleife → Channel-Schleife → FINISHED.
    Behält interne Zustände in self._* Feldern bei. Gibt IMMER ein Set zurück.
    """
    clip = self._clip
    scene = context.scene
    start_frame = self._start_frame

    # ---------- lokale Flag-Setter (nutzen deine bestehenden Felder) ----------
    def set_flag1(pattern, search):
        s = clip.tracking.settings
        s.default_pattern_size = int(pattern)
        s.default_search_size = int(search)
        s.default_margin = s.default_search_size  # deine Vorgabe

    def set_flag2(index):
        models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc']
        if 0 <= index < len(models):
            clip.tracking.settings.default_motion_model = models[index]

    def set_flag3(vv_index):
        # Mapping gemäß deiner Tabelle:
        # 0: R T, G F, B F
        # 1: R T, G T, B F
        # 2: R F, G T, B F
        # 3: R F, G T, B T
        # 4: R F, G F, B T
        s = clip.tracking.settings
        s.use_default_red_channel   = vv_index in (0, 1)
        s.use_default_green_channel = vv_index in (1, 2, 3)
        s.use_default_blue_channel  = vv_index in (3, 4)

    def detect_markers():
        # Deine Detektion (bewusst unverändert benannt)
        try:
            perform_marker_detection(context)
        except Exception:
            # Alternativer Hook aus deinem Code: marker_helper_main
            try:
                bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')
            except Exception as e:
                self.report({'ERROR'}, f"Marker-Detect fehlgeschlagen: {e}")
                raise

    def track_now():
        # Dein Tracking-Hook (falls du einen dedizierten Operator nutzt, hier einsetzen)
        # Standard: bidirektional/forward – wir rufen deinen Helper/Op auf:
        try:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT')  # ggf. ersetzen durch deinen Helper
        except Exception:
            # Fallback: versuche Exec (ohne Dialog)
            bpy.ops.clip.track_markers('EXEC_DEFAULT')

    def frames_after_start(track):
        cnt = 0
        for m in track.markers:
            try:
                if m.frame > start_frame and not getattr(m, "mute", False):
                    cnt += 1
            except Exception:
                pass
        return cnt

    def error_for_track(tr):
        # Nutze deinen Helper, fallweise defensiv
        try:
            return float(error_value(context, tr))
        except Exception:
            # Falls kein per-Track-Error möglich ist, Soft-Fallback:
            # vermeidet Division durch 0, aber verwässert die Metrik nicht.
            return 1.0

    def ega_score():
        # ega = Summe( f_i / e_i ) über alle selektierten Tracks
        total = 0.0
        any_selected = False
        for tr in clip.tracking.tracks:
            if getattr(tr, "select", False):
                any_selected = True
                f_i = frames_after_start(tr)
                e_i = max(error_for_track(tr), 1e-6)
                total += (f_i / e_i)
        # wenn nichts selektiert: 0
        return total if any_selected else 0.0

    # ---------- Initialisierung (einmalig) ----------
    if not hasattr(self, "_initialized") or not self._initialized:
        # Defaults setzen (pt, sus bereits vorbelegt); dg = 4 laut Vorgabe
        self._dg = 4 if self._dg == 0 else self._dg
        set_flag1(self._pt, self._sus)
        # Initial Detect & Track & Score
        detect_markers()
        track_now()
        ega = ega_score()
        # ev >= 0 ?
        if self._ev < 0:
            # nein → ev = ega, pt *= 1.1, sus = pt*2, flag1
            self._ev = ega
            self._pt = int(round(self._pt * 1.1))
            self._sus = int(self._pt * 2)
            set_flag1(self._pt, self._sus)
        # weiter in den Korridor-Zyklus
        self._initialized = True
        return {'RUNNING_MODAL'}

    # ---------- Korridor-Phase (dg) ----------
    if self._dg >= 0 and self._phase == 0:
        # Re-Detect/Track für aktuellen pt/sus
        detect_markers()
        track_now()
        ega = ega_score()

        if ega > self._ev:
            # ja → ev=ega, dg=4, ptv=pt, pt*=1.1, sus=pt*2, flag1
            self._ev = ega
            self._dg = 4
            self._ptv = self._pt
            self._pt = int(round(self._pt * 1.1))
            self._sus = int(self._pt * 2)
            set_flag1(self._pt, self._sus)
            return {'RUNNING_MODAL'}
        else:
            # nein → dg-1; wenn dg>=0 → pt wachsen, flag1; sonst Abschluss Korridor
            self._dg -= 1
            if self._dg >= 0:
                self._pt = int(round(self._pt * 1.1))
                self._sus = int(self._pt * 2)
                set_flag1(self._pt, self._sus)
                return {'RUNNING_MODAL'}
            else:
                # Korridor fertig → Pattern zurücksetzen auf bestes ptv
                self._pt = int(self._ptv) if self._ptv > 0 else self._pt
                self._sus = int(self._pt * 2)
                set_flag1(self._pt, self._sus)
                # Weiter zu Motion-Model-Phase
                self._mov = 0
                self._phase = 1
                return {'RUNNING_MODAL'}

    # ---------- Motion-Model-Phase ----------
    if self._phase == 1:
        # setze aktuelles Motion-Model
        set_flag2(self._mov)
        detect_markers()
        track_now()
        ega = ega_score()

        if ega > self._ev:
            # besser → ev aktualisieren, besten mov merken, aber wir testen weiter alle durch
            self._ev = ega
            best_mov = self._mov
        else:
            best_mov = None

        self._mov += 1
        if self._mov <= 5:
            # weitere Modelle testen
            return {'RUNNING_MODAL'}
        else:
            # alle Modelle durch → endgültiges setzen
            if best_mov is not None:
                set_flag2(best_mov)
                self._mov = best_mov
            # weiter zu Channels
            self._vf = 0
            self._best_vf = None
            self._best_ev_after_channels = self._ev
            self._phase = 2
            return {'RUNNING_MODAL'}

    # ---------- Channel-Phase ----------
    if self._phase == 2:
        set_flag3(self._vf)
        detect_markers()
        track_now()
        ega = ega_score()

        if ega > self._best_ev_after_channels:
            self._best_ev_after_channels = ega
            self._best_vf = self._vf

        self._vf += 1
        if self._vf <= 4:
            return {'RUNNING_MODAL'}
        else:
            # abgeschlossen → bestes Channel-Set setzen
            final_vf = self._best_vf if self._best_vf is not None else 0
            set_flag3(final_vf)
            print(f"[Optimize] Finished: pt={self._pt} sus={self._sus} mov={self._mov} ch={final_vf} ev={self._best_ev_after_channels:.3f}")
            return {'FINISHED'}

    # Fallback – sollte nicht erreicht werden
    return {'RUNNING_MODAL'}
