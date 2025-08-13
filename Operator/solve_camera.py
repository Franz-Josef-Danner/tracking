import bpy
from bpy.types import Operator
from ..Helper.refine_high_error import run_refine_on_high_error

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
    """Solve → Refine(1) → Re-Solve → Szene['solve_error'] setzen → Refine(2) mit diesem Threshold."""
    bl_idname = "clip.solve_watch_clean"
    bl_label = "Solve → Refine → Re-Solve → Persist & Refine"
    bl_options = {"INTERNAL", "REGISTER"}

    # Steuergrößen
    poll_interval: bpy.props.FloatProperty(
        name="Poll-Intervall (s)",
        default=0.2, min=0.05, max=2.0,
        description="Abfrageintervall"
    )
    # Threshold für den ERSTEN Refine-Durchlauf (vor dem Re-Solve)
    refine_error_threshold: bpy.props.FloatProperty(
        name="Refine(1) Frame Error ≥",
        default=2.0, min=0.0,
        description="Threshold für Refine(1) vor Re-Solve"
    )
    refine_limit_frames: bpy.props.IntProperty(
        name="Refine Max Frames",
        default=0, min=0,
        description="0 = alle Spike-Frames; sonst Obergrenze"
    )
    # Ob NACH dem zweiten Refine erneut gelöst werden soll
    refine_resolve_after: bpy.props.BoolProperty(
        name="Nach Refine(2) erneut lösen",
        default=False,
        description="Nach dem finalen Refine automatisch erneut Kamera lösen"
    )

    # interne Zustände
    _timer = None
    _phase = "init"             # init -> solved1 -> refined1 -> solved2 -> final_refine -> done
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
            # 1) Start Solve (1)
            if self._phase == "init":
                ovr = _clip_override(context)
                if not ovr:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, "CLIP_EDITOR-Kontext nicht verfügbar (Solve-Start).")
                    return {'CANCELLED'}
                try:
                    with context.temp_override(**ovr):
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                    self._phase = "solved1"
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Kamera-Solve (1) fehlgeschlagen: {ex}")
                    return {'CANCELLED'}

            # 2) Refine (1) mit vorgegebenem Threshold
            if self._phase == "solved1":
                try:
                    processed = run_refine_on_high_error(
                        context,
                        error_threshold=float(self.refine_error_threshold),
                        limit_frames=int(self.refine_limit_frames),
                        resolve_after=False  # Re-Solve folgt separat explizit
                    )
                    self.report({'INFO'}, f"Refine(1) abgeschlossen: {processed} Frame(s) ≥ {self.refine_error_threshold:.3f}px.")
                except Exception as e:
                    self.report({'WARNING'}, f"Refine(1) übersprungen: {e}")
                self._phase = "refined1"
                return {'RUNNING_MODAL'}

            # 3) Solve (2) nach Refine(1)
            if self._phase == "refined1":
                ovr = _clip_override(context)
                if not ovr:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, "CLIP_EDITOR-Kontext nicht verfügbar (Re-Solve).")
                    return {'CANCELLED'}
                try:
                    with context.temp_override(**ovr):
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                    self._phase = "solved2"
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Kamera-Solve (2) fehlgeschlagen: {ex}")
                    return {'CANCELLED'}

            # 4) Solve-Error lesen, in Szene persistieren, dann Refine (2) mit diesem Wert
            if self._phase == "solved2":
                recon = _get_reconstruction_safe(self._clip)
                avg_err = -1.0
                if recon and getattr(recon, "is_valid", False):
                    avg_err = float(getattr(recon, "average_error", -1.0))

                # Persistenz der Solve-KPI
                try:
                    context.scene["solve_error"] = float(avg_err)
                    print(f"[SolveWatch] Persistiert: scene['solve_error'] = {avg_err:.3f}")
                except Exception:
                    self.report({'WARNING'}, f"Solve Error konnte nicht gespeichert werden: {avg_err:.3f}")

                post = _count_markers(self._clip)
                delta = post - self._pre_marker_ct
                status = "weniger" if delta < 0 else ("mehr" if delta > 0 else "gleich")
                self.report({'INFO'}, f"Solve(2) OK (AvgErr={avg_err:.3f}). Marker: {post} ({status}, Δ={delta}).")

                # Refine (2) mit dem gespeicherten Wert als Threshold
                thr = float(context.scene.get("solve_error", avg_err))
                try:
                    processed2 = run_refine_on_high_error(
                        context,
                        error_threshold=None,          # <- Auto: nimmt scene["solve_error"]
                        limit_frames=int(self.refine_limit_frames),
                        resolve_after=bool(self.refine_resolve_after)
                    )
                    self.report({'INFO'}, f"Refine(2) abgeschlossen: {processed2} Frame(s) ≥ {thr:.3f}px.")
                except Exception as e:
                    self.report({'WARNING'}, f"Refine(2) übersprungen: {e}")

                self._cleanup_timer(context)
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

# ---- Public API (Export) -----------------------------------------------------

__all__ = ("CLIP_OT_solve_watch_clean", "run_solve_watch_clean")

def run_solve_watch_clean(context, poll_interval=0.2, **_compat):
    """
    Startet den Operator programmgesteuert.
    Hinweis: Zusätzliche/alte Parameter (z. B. cleanup_error) werden ignoriert.
    """
    return bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT', poll_interval=poll_interval)
