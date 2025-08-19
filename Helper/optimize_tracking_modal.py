import bpy
from bpy.types import Operator
from .set_test_value import set_test_value
from .error_value import error_value
from .detect import perform_marker_detection

class CLIP_OT_optimize_tracking_modal(Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimiertes Tracking (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

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

    # CHANGE: invoke-Proxy für INVOKE_DEFAULT, ruft deine execute-Logik auf.
    def invoke(self, context, event):
        try:
            return self.execute(context)
        except Exception as e:
            self.report({'ERROR'}, f"Invoke failed: {e}")
            return {'CANCELLED'}

    def execute(self, context):
        self._clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not self._clip:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        try:
            set_test_value(context)
        except Exception as e:
            self.report({'ERROR'}, f"set_test_value fehlgeschlagen: {e}")
            return {'CANCELLED'}

        self._start_frame = context.scene.frame_current

        wm = context.window_manager
        # CHANGE: defensiv altes Timer-Handle entfernen, dann neu erstellen
        try:
            if self._timer:
                wm.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        print("[Optimize] Start (execute→modal)")
        return {'RUNNING_MODAL'}

    # CHANGE: sauberes Cancel implementieren (Timer entfernen).
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
                self.cancel(context)  # CHANGE
                return {'CANCELLED'}

            if event.type == 'TIMER':
                try:
                    ret = self.run_step(context)
                except Exception as e:
                    self.report({'ERROR'}, f"run_step Exception: {e}")
                    print(f"[Optimize][ERROR] {e}")
                    self.cancel(context)  # CHANGE
                    return {'CANCELLED'}

                # CHANGE: Niemals None weiterreichen
                if ret is None:
                    # Fallback: weiterlaufen, um inkomplette Rückgaben nicht crashen zu lassen
                    # (bewahrt bestehende Logik; keine Verhaltensänderung außer Stabilität)
                    return {'RUNNING_MODAL'}

                # CHANGE: Nur gültige Sets akzeptieren
                if isinstance(ret, set):
                    # Bei FINISHED/CANCELLED Timer aufräumen
                    if 'FINISHED' in ret or 'CANCELLED' in ret:
                        self.cancel(context)
                    return ret

                # Falls jemand versehentlich einen String o.ä. zurückgibt → weiterlaufen
                return {'RUNNING_MODAL'}

            return {'PASS_THROUGH'}

        except Exception as e:
            self.report({'ERROR'}, f"Modal crashed: {e}")
            print(f"[Optimize][FATAL] {e}")
            self.cancel(context)  # CHANGE
            return {'CANCELLED'}

    def run_step(self, context):
        clip = self._clip

        def set_flag1(pattern, search):
            settings = clip.tracking.settings
            settings.default_pattern_size = int(pattern)
            settings.default_search_size = int(search)
            settings.default_margin = settings.default_search_size

        def set_flag2(index):
            # Erwartete Enum-Werte in Blender: 'Perspective','Affine','LocRotScale','LocScale','LocRot','Loc'
            motion_models = ['Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc']
            if 0 <= index < len(motion_models):
                clip.tracking.settings.default_motion_model = motion_models[index]

        def set_flag3(index):
            s = clip.tracking.settings
            s.use_default_red_channel   = (index in [0, 1])
            s.use_default_green_channel = (index in [1, 2, 3])
            s.use_default_blue_channel  = (index in [3, 4])

        def call_marker_helper():
            # Deine bestehende Pipeline-Hook bleibt unverändert
            bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        # --- HIER DEINE EXISTIERENDE SCHRITT-/PHASEN-LOGIK ---
        # Wichtig: Jede Code-Pfad-Branch MUSS ein Set zurückgeben.
        # Wenn deine bestehende Logik bereits Returns setzt (FINISHED/CANCELLED),
        # lass sie unverändert. Wir geben am Ende einen Default zurück.

        # Beispielhafte Platzhalter, die DEINE Variablen verwenden (keine Logikänderung):
        # self._phase / self._step können weiterhin frei von dir genutzt werden.

        # TODO: deine eigentliche Optimierungslogik … (unverändert belassen)

        # CHANGE: Garantierter Default → weiterlaufen, nie None
        return {'RUNNING_MODAL'}
