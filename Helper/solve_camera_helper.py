
import bpy
from bpy.types import Operator
from .find_low_marker_frame import find_low_marker_frame
from .jump_to_frame import jump_to_frame


def _clip_override(context):
    """Sichere CLIP_EDITOR-Overrides ermitteln."""
    for area in context.window.screen.areas:
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

class CLIP_OT_solve_watch_clean(Operator):
    """Startet Camera Solve, pollt Fertigstellung, führt Cleanup bei Error>2.0 aus und prüft Marker-Differenz."""
    bl_idname = "clip.solve_watch_clean"
    bl_label = "Solve → Watch → Clean (Error>2)"
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

    # interne Zustände
    _timer = None
    _started = False
    _pre_marker_ct = 0
    _post_cleanup = False
    _ovr = None
    _clip = None

    def invoke(self, context, event):
        self._ovr = _clip_override(context)
        if not self._ovr:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # Clip ermitteln & Vorher-Zustand erfassen
        with context.temp_override(**self._ovr):
            self._clip = _get_clip(context)
        if not self._clip:
            self.report({'ERROR'}, "Kein MovieClip verfügbar.")
            return {'CANCELLED'}

        self._pre_marker_ct = _count_markers(self._clip)
        self._post_cleanup = False
        self._started = False

        # Timer anlegen
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.poll_interval, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            # 1) Solve einmalig starten (im gültigen Override)
            if not self._started:
                try:
                    with context.temp_override(**self._ovr):
                        # Startet den Standard-Solve (Blockiert bis Abschluss, UI bleibt konsistent)
                        bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
                    self._started = True
                    return {'RUNNING_MODAL'}
                except Exception as ex:
                    self._cleanup_timer(context)
                    self.report({'ERROR'}, f"Kamera-Solve konnte nicht gestartet werden: {ex}")
                    return {'CANCELLED'}

            # 2) Solve-Fertig prüfen (robust über Reconstruction)
            recon = self._clip.tracking.objects.active.reconstruction
            # Best Practice: Fertig = gültige Rekonstruktion ODER durchschnittlicher Fehler aktualisiert (>0)
            is_done = bool(getattr(recon, "is_valid", False)) or (getattr(recon, "average_error", 0.0) > 0.0)

            if is_done and self._post_cleanup:
                # 4) Marker-Differenz prüfen
                post = _count_markers(self._clip)
                delta = post - self._pre_marker_ct
                status = "weniger" if delta < 0 else ("mehr" if delta > 0 else "gleich")
                avg_err = getattr(self._clip.tracking.objects.active.reconstruction, "average_error", -1.0)
            
                # --- NEU: Low-Marker-Recheck + Re-Trigger ---
                scene = context.scene
                marker_basis = scene.get("marker_basis", 25)
                frame = find_low_marker_frame(self._clip, marker_basis=marker_basis)  # nutzt deine Helper-Implementierung
            
                if frame is not None:
                    scene["goto_frame"] = int(frame)
                    # Im gültigen CLIP_EDITOR-Kontext: Playhead setzen + Pipeline erneut starten
                    try:
                        with context.temp_override(**self._ovr):
                            # Wichtig: Im Override-Kontext arbeiten, damit UI/Operatoren sicher laufen
                            jump_to_frame(bpy.context)  # nutzt die override-Context-Scene
                            bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                        self.report({'INFO'}, f"Solve OK (AvgErr={avg_err:.3f}). Low-Marker-Frame {frame} gefunden → Playhead gesetzt, Pipeline neu gestartet.")
                    except Exception as ex:
                        self.report({'WARNING'}, f"Solve OK (AvgErr={avg_err:.3f}). Low-Marker-Frame {frame} gefunden, aber Re-Trigger scheiterte: {ex}")
                    finally:
                        self._cleanup_timer(context)
                    return {'FINISHED'}
            
                # Kein Low-Marker-Frame → wie bisher sauber beenden
                self.report({'INFO'}, f"Solve OK (AvgErr={avg_err:.3f}). Marker danach: {post} ({status}, Δ={delta}). Cleanup error>{self.cleanup_error:.2f}.")
                self._cleanup_timer(context)
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
