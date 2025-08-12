import bpy
from bpy.types import Operator
from .refine_on_high_error import run_refine_on_high_error  # NEU

def _clip_override(context):
    """Sichere CLIP_EDITOR-Overrides ermitteln (immer frisch abrufen)."""
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
    # Fallback: erstes MovieClip aus Datenbank
    return bpy.data.movieclips[0] if bpy.data.movieclips else None

def _count_markers(clip) -> int:
    """Summe aller Marker-Keyframes über alle Tracks."""
    if not clip:
        return 0
    total = 0
    for tr in clip.tracking.tracks:
        total += len(tr.markers)
    return total

def _get_reconstruction_safe(clip):
    """Reconstruction sicher holen (None-safe)."""
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
    """Startet Camera Solve, prüft Fertigstellung robust, führt Cleanup bei Error-Schwelle aus und vergleicht Marker-Differenz."""
    bl_idname = "clip.solve_watch_clean"
    bl_label = "Solve → Watch → Clean (Error>Schwellwert)"
    bl_options = {"INTERNAL", "REGISTER"}

    poll_interval: bpy.props.FloatProperty(
        name="Poll-Intervall (s)",
        default=0.2, min=0.05, max=2.0,
        description="Abfrageintervall für Solve-Status"
    )
    cleanup_error: bpy.props.FloatProperty(
        name="Cleanup Error",
        default=2.0, min=0.0,
        description="Schwellwert für bpy.ops.clip.clean_tracks(error=...)"
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
    _phase = "init"           # init -> solved -> cleaned -> done
    _pre_marker_ct = 0
    _clip = None

    def invoke(self, context, event):
        # Clip ermitteln & Vorher-Zustand erfassen (im gültigen Override)
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

        # Timer anlegen
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
                        # WICHTIG: Kein weiterer Modal-Stack
                        bpy.ops.clip.solve_camera('EXEC_DEFAULT')
                    self._phase = "solved"
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Kamera-Solve fehlgeschlagen: {ex}")
                    return {'CANCELLED'}

            # PHASE: solved -> Error prüfen und ggf. Cleanup ausführen
            if self._phase == "solved":
                recon = _get_reconstruction_safe(self._clip)
                avg_err = getattr(recon, "average_error", 0.0) if recon else 0.0

                # Cleanup läuft immer mit deiner Schwellwert-Logik
                ovr = _clip_override(context)
                if not ovr:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, "CLIP_EDITOR-Kontext nicht verfügbar (Cleanup).")
                    return {'CANCELLED'}
                try:
                    with context.temp_override(**ovr):
                        bpy.ops.clip.clean_tracks(frames=0, error=self.cleanup_error, action='DELETE_TRACK')
                    self._phase = "cleaned"
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Cleanup fehlgeschlagen: {ex}")
                    return {'CANCELLED'}

            # PHASE: cleaned -> Marker-Differenz loggen, Timer schließen, Main starten (EXEC)
            if self._phase == "cleaned":
                recon = _get_reconstruction_safe(self._clip)
                avg_err = getattr(recon, "average_error", -1.0) if recon else -1.0

                post = _count_markers(self._clip)
                delta = post - self._pre_marker_ct
                status = "weniger" if delta < 0 else ("mehr" if delta > 0 else "gleich")

                self.report({'INFO'}, f"Solve OK (AvgErr={avg_err:.3f}). Marker danach: {post} ({status}, Δ={delta}). Cleanup error>{self.cleanup_error:.2f}.")

                # Timer zuerst sauber entfernen, dann Main ohne weiteren Modal-Stack starten
                self._cleanup_timer(context)

                ovr = _clip_override(context)
                if not ovr:
                    # Ohne gültigen Kontext kein fataler Fehler – Operator ist fertig
                    return {'FINISHED'}
                # Timer zuerst sauber entfernen
                self._cleanup_timer(context)

                # --- STATT MAIN: Refine-on-High-Error triggern (NEU) ---
                try:
                    processed = run_refine_on_high_error(
                        context,
                        error_threshold=self.refine_error_threshold,
                        limit_frames=self.refine_limit_frames,
                        resolve_after=self.refine_resolve_after
                    )
                    self.report({'INFO'}, f"Refine abgeschlossen: {processed} Frame(s) ≥ {self.refine_error_threshold:.3f}px.")
                except Exception as e:
                    # Nicht fatal – Solve/ Cleanup waren erfolgreich; wir loggen nur.
                    self.report({'WARNING'}, f"Refine übersprungen: {e}")

                self._phase = "done"
                return {'FINISHED'}
        # Abbruch via ESC/RIGHTMOUSE
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

# Optional: schlanke Start-API für andere Funktionen
def run_solve_watch_clean(context, poll_interval=0.2, cleanup_error=2.0):
    """Helper-Funktion, um den Operator programmatic zu starten."""
    return bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT', poll_interval=poll_interval, cleanup_error=cleanup_error)
