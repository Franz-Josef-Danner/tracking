# Helper/optimize_tracking_modal.py  (jetzt sauberer Modal-Operator)
# Fixes:
# - modal() & run_step() liefern IMMER ein set (RUNNING_MODAL / FINISHED / CANCELLED / PASS_THROUGH)
# - sauberer Timer-Cleanup in cancel()
# - defensive Guards (fehlender Clip/Context)
# - eindeutiges Logging pro Phase/Step

from __future__ import annotations
import bpy
from bpy.types import Operator

# lokale Imports – passen Sie ggf. den relativen Pfad an, falls die Module in einem anderen Package liegen
from .set_test_value import set_test_value
from .error_value import error_value
from .detect import run_detect_once


class CLIP_OT_optimize_tracking_modal(Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # --- interne Zustände / Felder ---
    _timer = None
    _step = 0                # Schrittzähler innerhalb einer Phase
    _phase = 0               # 0: Init, 1: Detect, 2: Trial(s), 3: Finalize
    _clip = None

    # Parameterkandidaten (Beispielwerte / Defaults)
    _ev = -1                 # error-value placeholder
    _dg = 0
    _pt = 21                 # pattern size
    _ptv = 21                # variant holder
    _sus = 42                # search size
    _mov = 0                 # motion-model index
    _vf = 0                  # channel variant index

    _start_frame = 0
    _stable_count = 0
    _prev_marker_count = -1
    _prev_frame = -1

    # Konfiguration
    _timer_interval = 0.2
    _max_trials = 8          # Anzahl Test-Varianten in Phase 2 (Anpassen an Ihr Konzept)
    _trial_index = 0

    # ------------- Utility: Logging -------------
    def _log(self, msg: str):
        print(f"[Optimize] {msg}")

    # ------------- Operator Lifecycle -------------
    def execute(self, context):
        # Context/Clip prüfen
        space = getattr(context, "space_data", None)
        self._clip = getattr(space, "clip", None) if space else None
        if not self._clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        # Pre-Setup
        try:
            # je nach Implementierung: set_test_value(context) oder set_test_value(context.scene)
            set_test_value(context)
        except Exception as ex:
            self._log(f"set_test_value Fehler: {ex}")

        self._start_frame = context.scene.frame_current
        self._phase = 0
        self._step = 0
        self._trial_index = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1

        # Timer setzen & Modal-Handler registrieren
        wm = context.window_manager
        self._timer = wm.event_timer_add(self._timer_interval, window=context.window)
        wm.modal_handler_add(self)
        self._log(f"Start (frame={self._start_frame})")
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        # Timer sauber entfernen
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        finally:
            self._timer = None
        self._log("Cancel/Cleanup done.")

    def modal(self, context, event):
        try:
            # ESC → Nutzerabbruch
            if event.type == 'ESC':
                self.report({'WARNING'}, "Tracking-Optimierung manuell abgebrochen.")
                self.cancel(context)
                return {'CANCELLED'}

            # TICK
            if event.type == 'TIMER':
                return self.run_step(context)

            # alles andere durchreichen
            return {'PASS_THROUGH'}

        except Exception as ex:
            # Niemals None zurückgeben – immer canceln und melden
            self.report({'ERROR'}, f"modal() Fehler: {ex}")
            self.cancel(context)
            return {'CANCELLED'}

    # ------------- Kernlogik -------------
    def run_step(self, context):
        """
        Muss IMMER ein set zurückgeben.
        """
        # Context/Clip weiterhin vorhanden?
        if not context or not getattr(context, "window_manager", None):
            self._log("Context verloren – Abbruch.")
            self.cancel(context)
            return {'CANCELLED'}
        if not self._clip:
            self._log("Clip verloren – Abbruch.")
            self.cancel(context)
            return {'CANCELLED'}

        try:
            if self._phase == 0:
                # INIT/Preflight
                if self._step == 0:
                    self._log("Step 0: Preflight")
                    self._step += 1
                    return {'RUNNING_MODAL'}

                # weiter zu Detect
                self._phase = 1
                self._step = 0
                return {'RUNNING_MODAL'}

            elif self._phase == 1:
                # Einmaliger Detect am Startframe
                if self._step == 0:
                    self._log("Step 1: Detect@Startframe")
                    ok = False
                    try:
                        ok = bool(run_detect_once(context, frame=self._start_frame))
                    except TypeError:
                        # Fallback ohne named args
                        ok = bool(run_detect_once(context))
                    except Exception as ex:
                        self._log(f"Detect Fehler: {ex}")
                        ok = False

                    if not ok:
                        self.report({'ERROR'}, "Detect fehlgeschlagen.")
                        self.cancel(context)
                        return {'CANCELLED'}

                    self._step += 1
                    return {'RUNNING_MODAL'}

                # weiter zu Trials
                self._phase = 2
                self._step = 0
                self._trial_index = 0
                return {'RUNNING_MODAL'}

            elif self._phase == 2:
                # Trials über Parameter-Varianten
                if self._trial_index >= self._max_trials:
                    self._log("Trials abgeschlossen → Finalize")
                    self._phase = 3
                    self._step = 0
                    return {'RUNNING_MODAL'}

                # Beispiel: einfache Variantenschleife
                self._log(f"Trial {self._trial_index}: (Pattern/Search/Motion/Channels) → Score")
                self._apply_flags_for_trial(self._trial_index)

                # → Hier Tracking/Scoring-Logik einhängen (verkürzt dargestellt)
                #    z.B. bpy.ops.clip.marker_helper_main('EXEC_DEFAULT') etc.
                try:
                    # Platzhalter: Error-/Score-Ermittlung
                    self._ev = error_value(self._clip)
                except Exception as ex:
                    self._log(f"error_value Fehler: {ex}")
                    self._ev = -1

                self._trial_index += 1
                return {'RUNNING_MODAL'}

            elif self._phase == 3:
                # Finalize: beste Variante setzen, Cleanup, Ende
                if self._step == 0:
                    self._log("Step 3: Finalize (beste Flags übernehmen)")
                    # TODO: hier die beste Variante dauerhaft setzen
                    self._step += 1
                    return {'RUNNING_MODAL'}

                # Fertig
                self._log("Fertig.")
                self.cancel(context)
                return {'FINISHED'}

            else:
                # Unerwartete Phase → abbrechen
                self._log(f"Unbekannte Phase {self._phase} – Abbruch.")
                self.cancel(context)
                return {'CANCELLED'}

        except Exception as ex:
            # Sicherheitsnetz – niemals None zurückgeben
            self.report({'ERROR'}, f"run_step() Fehler: {ex}")
            self.cancel(context)
            return {'CANCELLED'}

    # ------------- Flags/Parameter setzen -------------
    def _apply_flags_for_trial(self, idx: int):
        """
        Beispielhafte Parametrisierung. Passen Sie Mapping/Logik an Ihre echte Optimierung an.
        """
        clip = self._clip
        s = clip.tracking.settings

        # --- Pattern/Search ---
        # einfache Variation: alterniere +/- um Basiswerte
        base_pattern = max(9, self._pt)
        base_search = max(18, self._sus)
        variant = (idx % 4)
        pattern = base_pattern + (variant * 4)
        search = base_search + (variant * 8)
        s.default_pattern_size = int(pattern)
        s.default_search_size = int(search)
        s.default_margin = s.default_search_size
        self._log(f"Flags1: pattern={s.default_pattern_size}, search={s.default_search_size}, margin={s.default_margin}")

        # --- Motion-Model ---
        motion_models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc']
        mm_idx = (idx // 4) % len(motion_models)
        s.default_motion_model = motion_models[mm_idx]
        self._log(f"Flags2: motion={s.default_motion_model}")

        # --- Channels ---
        ch_idx = (idx // (4 * len(motion_models))) % 5  # 0..4
        s.use_default_red_channel = (ch_idx in [0, 1])
        s.use_default_green_channel = (ch_idx in [1, 2, 3])
        s.use_default_blue_channel = (ch_idx in [3, 4])
        self._log(f"Flags3: channels=R{int(s.use_default_red_channel)} G{int(s.use_default_green_channel)} B{int(s.use_default_blue_channel)}")


# ---------- Register ----------
def register():
    bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)
    print("[Optimize] operator registered")

def unregister():
    bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
    print("[Optimize] operator unregistered")
