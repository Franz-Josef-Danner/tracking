import bpy
from bpy.types import Operator
from .refine_high_error import run_refine_on_high_error

def _clip_override(context):
    win = context.window
    if not win:
        return None
    scr = win.screen if hasattr(win, "screen") else None
    if not scr:
        return None
    for area in scr.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'area': area, 'region': region, 'space_data': area.spaces.active}
    return None

def _get_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None

def _count_markers(clip) -> int:
    if not clip:
        return 0
    return sum(len(tr.markers) for tr in clip.tracking.tracks)

def _get_reconstruction_safe(clip):
    if not clip:
        return None
    tracking = getattr(clip, "tracking", None)
    if not tracking:
        return None
    objects = getattr(tracking, "objects", None)
    if not objects:
        return None
    active = getattr(objects, "active", None)
    if not active:
        return None
    return getattr(active, "reconstruction", None)

class CLIP_OT_solve_watch_clean(Operator):
    """Startet Camera Solve und überwacht die Fertigstellung. Keine Löschaktionen."""
    bl_idname = "clip.solve_watch_clean"  # Kompatibilität beibehalten
    bl_label = "Solve → Watch (kein Delete)"
    bl_options = {"INTERNAL", "REGISTER"}

    poll_interval: bpy.props.FloatProperty(
        name="Poll-Intervall (s)",
        default=0.2, min=0.05, max=2.0,
        description="Abfrageintervall für Solve-Status"
    )
    refine_error_threshold: bpy.props.FloatProperty(
        name="Refine Frame Error ≥",
        default=2.0, min=0.0,
        description="Per-Frame Solve-Error (px), ab dem beidseitig Refine läuft"
    )
    refine_limit_frames: bpy.props.IntProperty(
        name="Refine Max Frames",
        default=0, min=0,
        description="0 = alle Spike-Frames; sonst Obergrenze"
    )
    refine_resolve_after: bpy.props.BoolProperty(
        name="Nach Refine erneut lösen",
        default=False,
        description="Nach dem Refine automatisch erneut Kamera lösen"
    )

    # interne Zustände
    _timer = None
    _phase = "init"           # init -> solved -> done
    _pre_marker_ct = 0
    _clip = None

    def invoke(self, context, event):
        ovr = _clip_override(context)
        if not ovr:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        with context.temp_override(**ovr):
            self._clip = _get_clip(context)

        if not self._clip:
            self.report({'ERROR'}, "Kein MovieClip verfügbar.")
            return {'CANCELLED'}

        self._pre_marker_ct = _count_markers(self._clip)
        self._phase = "init"

        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            # PHASE: init -> Solve synchron per EXEC_DEFAULT ausführen
            if self._phase == "init":
                ovr = _clip_override(context)
                if not ovr:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, "CLIP_EDITOR-Kontext nicht verfügbar (Solve-Start).")
                    return {'CANCELLED'}
                try:
                    with context.temp_override(**ovr):
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                    self._phase = "solved"
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Kamera-Solve fehlgeschlagen: {ex}")
                    return {'CANCELLED'}

            # PHASE: solved -> Direkt Abschluss ohne Cleanup
            if self._phase == "solved":
                recon = _get_reconstruction_safe(self._clip)
                avg_err = getattr(recon, "average_error", -1.0) if recon else -1.0

                post = _count_markers(self._clip)
                delta = post - self._pre_marker_ct
                status = "weniger" if delta < 0 else ("mehr" if delta > 0 else "gleich")

                self.report({'INFO'}, f"Solve OK (AvgErr={avg_err:.3f}). Marker danach: {post} ({status}, Δ={delta}).")

                self._cleanup_timer(context)

                # Optional: Refine-on-High-Error
                try:
                    processed = run_refine_on_high_error(
                        context,
                        error_threshold=self.refine_error_threshold,
                        limit_frames=self.refine_limit_frames,
                        resolve_after=self.refine_resolve_after
                    )
                    self.report({'INFO'}, f"Refine abgeschlossen: {processed} Frame(s) ≥ {self.refine_error_threshold:.3f}px.")
                except Exception as e:
                    self.report({'WARNING'}, f"Refine übersprungen: {e}")

                self._phase = "done"
                return {'FINISHED'}

        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._cleanup_timer(context)
            self.report({'INFO'}, "Abgebrochen.")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _cleanup_timer(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
