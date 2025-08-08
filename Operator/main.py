# Operator/main.py
import bpy
from bpy.types import Operator


# ---------- Helfer -----------------------------------------------------------

def _find_clip_context(context):
    """Finde gültigen CLIP_EDITOR-UI-Kontext (area, region, space)."""
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


def _count_active_markers_at_frame(clip, frame):
    """Zählt Marker, die im Frame existieren und nicht gemutet sind."""
    if not clip:
        return 0
    tracks = clip.tracking.tracks
    c = 0
    for t in tracks:
        m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            c += 1
    return c


def _find_frame_with_too_few_markers(scene, clip, min_markers, log_stride=25):
    """Gibt ersten Frame mit weniger als min_markers aktiven Markern zurück (oder None)."""
    if not clip:
        return None

    start, end = scene.frame_start, scene.frame_end
    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {min_markers}")

    for f in range(start, end + 1):
        cnt = _count_active_markers_at_frame(clip, f)
        if (f % log_stride == 0) or f in (start, end):
            print(f"[MarkerCheck] Frame {f}: {cnt} aktive Marker")
        if cnt < min_markers:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {f}")
            return f
    return None


# ---------- Main-Operator ----------------------------------------------------

class CLIP_OT_main(Operator):
    """Orchestriert: tracking_pipeline → Markercheck (Loop) → clean_error_tracks"""
    bl_idname = "clip.main"
    bl_label = "Tracking + Cleanup (Main)"
    bl_options = {'REGISTER', 'UNDO'}

    min_markers: bpy.props.IntProperty(
        name="Min. Marker pro Frame",
        default=20,
        min=0,
        soft_max=200
    )

    verbose: bpy.props.BoolProperty(
        name="Verbose",
        default=True
    )

    _timer = None
    _state = "IDLE"  # IDLE -> RUN_PIPELINE -> WAIT_PIPELINE -> CHECK -> CLEANUP -> DONE

    def execute(self, context):
        # Clip-Kontext sicherstellen
        area, region, space = _find_clip_context(context)
        if not space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # Status-Flags zurücksetzen
        scene = context.scene
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""

        # Modal-Timer starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)

        # Pipeline anwerfen
        self._state = "RUN_PIPELINE"
        if self.verbose:
            print("[Main] Starte Pipeline…")
        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.report({'WARNING'}, "Abgebrochen.")
            return self._finish(context, cancelled=True)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        # 1) Transition: RUN_PIPELINE → WAIT_PIPELINE
        if self._state == "RUN_PIPELINE":
            self._state = "WAIT_PIPELINE"
            return {'PASS_THROUGH'}

        # 2) Pipeline-Fortschritt beobachten
        if self._state == "WAIT_PIPELINE":
            if scene.get("pipeline_status", "") == "done":
                scene["pipeline_status"] = ""
                if self.verbose:
                    print("[Main] Pipeline fertig → Markercheck")
                self._state = "CHECK"
            return {'PASS_THROUGH'}

        # 3) Markerprüfung & ggf. erneuter Durchlauf
        if self._state == "CHECK":
            area, region, space = _find_clip_context(context)
            if not space:
                self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext für Markercheck.")
                return self._finish(context, cancelled=True)

            clip = space.clip
            bad_frame = _find_frame_with_too_few_markers(scene, clip, self.min_markers)

            if bad_frame is not None:
                # Zu wenig Marker → an Frame springen & Pipeline neu starten
                with context.temp_override(area=area, region=region, space_data=space):
                    scene.frame_set(bad_frame)
                if self.verbose:
                    print(f"[Main] Neuer Durchlauf: springe zu Frame {bad_frame} und starte Pipeline erneut.")
                self._state = "RUN_PIPELINE"
                with context.temp_override(area=area, region=region, space_data=space):
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                return {'PASS_THROUGH'}

            # Sonst weiter zum Cleanup
            self._state = "CLEANUP"
            return {'PASS_THROUGH'}

        # 4) Einmaliger Error-Cleanup mit EXEC_DEFAULT (UI-Feedback)
        if self._state == "CLEANUP":
            area, region, space = _find_clip_context(context)
            if not space:
                self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext für Error-Cleanup.")
                return self._finish(context, cancelled=True)

            if self.verbose:
                print("[Main] Starte Error-Cleanup…")
            with context.temp_override(area=area, region=region, space_data=space):
                bpy.ops.clip.clean_error_tracks('EXEC_DEFAULT', verbose=True)

            self._state = "DONE"
            return {'PASS_THROUGH'}

        # 5) Fertig
        if self._state == "DONE":
            if self.verbose:
                print("[Main] Tracking + Markerprüfung abgeschlossen.")
            return self._finish(context)

        return {'PASS_THROUGH'}

    # --------- intern --------------------------------------------------------

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        return {'CANCELLED' if cancelled else 'FINISHED'}
