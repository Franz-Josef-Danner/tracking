# Operator/track_operator.py
import bpy
from typing import List, Tuple
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_end_frame
# optional:
# from ..Helper.motion_model import select_best_motion_model


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def _find_clip_editor_area(clip):
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            for space in area.spaces:
                if space.type == "CLIP_EDITOR" and (getattr(space, "clip", None) == clip or space.clip is None):
                    region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
                    if region_window:
                        return window, area, region_window, space
    return None, None, None, None


def _collect_selected_track_names(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip or not hasattr(clip, "tracking"):
        return []
    return [t.name for t in clip.tracking.tracks if t.select]


# ------------------------------------------------------------
# Modal Operator – Vorwärts mit Analyse
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Nicht blockierender Vorwärts-Tracking-Zyklus mit Analyse-Phase (apply_formula_on_selected_tracks)."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Vorwärts, Sichtbar + Analyse)"
    bl_options = {"REGISTER", "INTERNAL"}

    timer = None
    processing_names = []
    current_frame = 0
    frame_start = 0
    frame_end = 0
    frames_processed = 0
    max_frames: bpy.props.IntProperty(default=0, min=0, soft_max=100000)

    # --------------------------------------------------------
    # invoke() – Initialisierung
    # --------------------------------------------------------
    def invoke(self, context, event):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            self.report({'ERROR'}, "Kein CLIP_EDITOR aktiv.")
            return {'CANCELLED'}

        self.window, self.area, self.region, self.space = window, area, region, space
        self.scene, self.clip, self.tracking = scene, clip, clip.tracking
        self.frame_start = ph_get_start_frame(context)
        self.frame_end = get_end_frame(context)
        self.current_frame = max(self.frame_start, int(scene.frame_current))
        self.processing_names = _collect_selected_track_names(context)
        self.start_frame_saved = self.current_frame
        self.frames_processed = 0

        if not self.processing_names:
            self.report({'ERROR'}, "Keine Tracks selektiert.")
            return {'CANCELLED'}

        # Timer für Modalbetrieb (UI bleibt reaktiv)
        self.timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        print(f"[Kaiserlich Tracker][Modal Forward] Starte Vorwärts-Tracking (Analyse aktiv) ab Frame {self.current_frame}")
        return {'RUNNING_MODAL'}

    # --------------------------------------------------------
    # modal() – pro Frame ein Schritt
    # --------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            print("[Kaiserlich Tracker][Modal Forward] ⏹ Abbruch durch Benutzer.")
            return self._finish(context, cancelled=True)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Stopkriterien
        if self.current_frame >= self.frame_end:
            print(f"[Kaiserlich Tracker][Modal Forward] Szenenende erreicht ({self.frame_end}).")
            return self._finish(context)
        if not self.processing_names:
            print("[Kaiserlich Tracker][Modal Forward] Keine aktiven Tracks mehr.")
            return self._finish(context)
        if self.max_frames > 0 and self.frames_processed >= self.max_frames:
            print("[Kaiserlich Tracker][Modal Forward] Sicherheitslimit erreicht.")
            return self._finish(context)

        # --------------------------------------------------------
        # Analyse-Hook (Motion Model / KPI / Threshold)
        # --------------------------------------------------------
        try:
            # Optional: KI-basiertes Motion-Model-Tuning
            # best_model = select_best_motion_model(context, frame=self.current_frame)
            # if best_model:
            #     self.clip.tracking.settings.motion_model = best_model

            # Standard-Analyse
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Modal Forward] Analyse-Fehler: {e}")

        # --------------------------------------------------------
        # Tracking-Schritt
        # --------------------------------------------------------
        with bpy.context.temp_override(window=self.window, area=self.area, region=self.region, space_data=self.space):
            try:
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            except Exception as e:
                print(f"[Kaiserlich Tracker][Modal Forward] Tracking-Fehler: {e}")
                return self._finish(context)

        # Fortschritt sichtbar machen
        if self.space.clip_user.frame_current == self.current_frame:
            self.current_frame += 1
        else:
            self.current_frame = self.space.clip_user.frame_current

        if self.current_frame > self.frame_end:
            self.current_frame = self.frame_end

        self.scene.frame_current = self.current_frame
        context.area.tag_redraw()
        self.frames_processed += 1

        print(f"[Kaiserlich Tracker][Modal Forward] Frame {self.current_frame} analysiert + getrackt ({self.frames_processed})")
        return {'RUNNING_MODAL'}

    # --------------------------------------------------------
    # Abschluss / Cleanup
    # --------------------------------------------------------
    def _finish(self, context, cancelled=False):
        if self.timer:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        try:
            reset_to_frame(context, self.start_frame_saved)
        except Exception:
            pass

        if cancelled:
            print("[Kaiserlich Tracker][Modal Forward] ❌ Abgebrochen.")
            return {'CANCELLED'}

        print("[Kaiserlich Tracker][Modal Forward] ✅ Fertig.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)
