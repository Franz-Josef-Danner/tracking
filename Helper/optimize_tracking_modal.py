# tracking-test/Helper/optimize_tracking_modal.py
from __future__ import annotations
import bpy
from bpy.types import Operator

# Externe Helper optional (defensiv importieren, damit die Klassendefinition nie scheitert)
try:
    from .set_test_value import set_test_value
except Exception:
    set_test_value = None

try:
    from .error_value import error_value
except Exception:
    error_value = None

try:
    from .detect import perform_marker_detection
except Exception:
    perform_marker_detection = None

__all__ = ["CLIP_OT_optimize_tracking_modal"]

class CLIP_OT_optimize_tracking_modal(Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------ interne Zustände (wie bei dir) ------------------
    _timer = None
    _step = 0
    _phase = 0
    _clip = None

    _ev = -1
    _dg = 0
    _pt = 21
    _ptv = 21
    _sus = 42
    _mov = 0
    _vf = 0

    _start_frame = 0
    _stable_count = 0
    _prev_marker_count = -1
    _prev_frame = -1

    # ------------------ Lifecycle ------------------
    def invoke(self, context, event):
        # INVOKE_DEFAULT → leite auf execute um (deine Logik)
        return self.execute(context)

    def execute(self, context):
        # Clip resolven
        self._clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not self._clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        # set_test_value (optional)
        if set_test_value is not None:
            try:
                set_test_value(context)
            except Exception as e:
                self.report({'WARNING'}, f"set_test_value: {e}")

        self._start_frame = context.scene.frame_current

        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        if not win:
            self.report({'ERROR'}, "Kein aktives Window – TIMER kann nicht registriert werden.")
            return {'CANCELLED'}

        # alten Timer sauber entfernen (falls vorhanden)
        try:
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass

        # Timer + Modal-Handler registrieren
        self._timer = wm.event_timer_add(0.2, window=win)
        wm.modal_handler_add(self)

        # Kick für Event-Loop
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        print("[Optimize] Start (execute→modal)")
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None

    def modal(self, context, event):
        try:
            if event.type == 'ESC':
                self.report({'WARNING'}, "Tracking-Optimierung manuell abgebrochen.")
                self.cancel(context)
                return {'CANCELLED'}

            if event.type == 'TIMER':
                # Deine Schrittlogik – MUSS ein Set zurückgeben
                try:
                    ret = self.run_step(context)
                except Exception as e:
                    self.report({'ERROR'}, f"run_step: {e}")
                    self.cancel(context)
                    return {'CANCELLED'}

                if not isinstance(ret, set):
                    # Fallback: nie None zurückgeben
                    ret = {'RUNNING_MODAL'}

                if 'FINISHED' in ret or 'CANCELLED' in ret:
                    self.cancel(context)
                return ret

            return {'PASS_THROUGH'}

        except Exception as e:
            self.report({'ERROR'}, f"Modal crashed: {e}")
            self.cancel(context)
            return {'CANCELLED'}

    # ------------------ Deine Schrittlogik (1:1 integriert) ------------------
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
            if perform_marker_detection is not None:
                perform_marker_detection(context)
            else:
                # Alternativer Hook aus deinem Code: marker_helper_main
                bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

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
                if error_value is not None:
                    return float(error_value(context, tr))
            except Exception:
                pass
            # Falls kein per-Track-Error möglich ist, Soft-Fallback:
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
