# Operator/main.py
import bpy
from bpy.types import Operator

# ---------- kleine Helfer ----------------------------------------------------

def _find_clip_context(context):
    """Finde gültigen CLIP_EDITOR-UI-Kontext (area, region, space) für Operator-Aufrufe."""
    clip_area = clip_region = clip_space = None
    for a in context.screen.areas:
        if a.type == 'CLIP_EDITOR':
            for r in a.regions:
                if r.type == 'WINDOW':
                    clip_area = a
                    clip_region = r
                    clip_space = a.spaces.active
                    return clip_area, clip_region, clip_space
    return None, None, None


def _count_active_markers_at_frame(clip, frame):
    """
    'Aktive Marker' = Marker, die in diesem Frame existieren und nicht gemutet sind.
    """
    if not clip:
        return 0
    tracks = clip.tracking.tracks
    c = 0
    for t in tracks:
        m = t.markers.find_frame(frame)
        if m and not getattr(m, "mute", False):
            c += 1
    return c


def _find_frame_with_too_few_markers(context, min_markers):
    """
    Scannt die Timeline. Gibt den ersten Frame mit weniger als min_markers aktiven Markern zurück,
    sonst None. Gibt dabei minimale Console-Logs als Progress.
    """
    scene = context.scene
    clip = context.space_data.clip if context.space_data and context.space_data.type == 'CLIP' else None
    if not clip:
        return None

    start, end = scene.frame_start, scene.frame_end

    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {min_markers}")
    bad_frame = None
    for f in range(start, end + 1):
        cnt = _count_active_markers_at_frame(clip, f)
        if f % 25 == 0 or f in (start, end):
            # gelegentliches UI-Feedback, damit nichts „einfriert“
            print(f"[MarkerCheck] Frame {f}: {cnt} aktive Marker")
        if cnt < min_markers and bad_frame is None:
            bad_frame = f
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {f}")
            break

    return bad_frame


# ---------- Main-Operator ----------------------------------------------------

class CLIP_OT_main(Operator):
    """Orchestriert: tracking_pipeline → Markercheck (Loop) → clean_error_tracks"""
    bl_idname = "clip.main"
    bl_label = "Tracking + Cleanup (Main)"
    bl_options = {'REGISTER', 'UNDO'}

    # Minimal einstellbar, falls du im Panel einen Slider anbinden willst.
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
        # Sicherstellen, dass wir im Clip-Editor aufgerufen werden können
        area, region, space = _find_clip_context(context)
        if not space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # Status-Flags zurücksetzen
        scene = context.scene
        scene["pipeline_status"] = ""
        scene["detect_status"] = ""
        scene["bidirectional_status"] = ""

        # Modal starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)

        self._state = "RUN_PIPELINE"
        if self.verbose:
            print("[Main] Starte Pipeline…")

        # pipeline direkt starten
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

        # Zustand: Warten bis pipeline fertig
        if self._state == "RUN_PIPELINE":
            self._state = "WAIT_PIPELINE"
            return {'PASS_THROUGH'}

        if self._state == "WAIT_PIPELINE":
            if scene.get("pipeline_status", "") == "done":
                # Flag leeren, weiter zum Check
                scene["pipeline_status"] = ""
                self._state = "CHECK"
                if self.verbose:
                    print("[Main] Pipeline fertig → Markercheck")
            return {'PASS_THROUGH'}

        if self._state == "CHECK":
            area, region, space = _find_clip_context(context)
            if not space:
                self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext für Markercheck.")
                return self._finish(context, cancelled=True)

            # Frame mit zu wenigen Markern?
            bad = _find_frame_with_too_few_markers(context, self.min_markers)
            if bad is not None:
                # Frame setzen und Pipeline erneut starten
                with context.temp_override(area=area, region=region, space_data=space):
                    context.scene.frame_set(bad)
                if self.verbose:
                    print(f"[Main] Neuer Durchlauf: springe zu Frame {bad} und starte Pipeline erneut.")
                self._state = "RUN_PIPELINE"
                with context.temp_override(area=area, region=region, space_data=space):
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                return {'PASS_THROUGH'}

            # Sonst: Cleanup ausführen (einmal)
            self._state = "CLEANUP"
            return {'PASS_THROUGH'}

        if self._state == "CLEANUP":
            # Cleanup nur EINMAL und mit gültigem CLIP-Kontext + EXEC_DEFAULT
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

        if cancelled:
            return {'CANCELLED'}
        return {'FINISHED'}

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                scene["goto_frame"] = frame
                jump_to_frame(context)

                key = str(frame)
                entry = next((e for e in repeat_collection if e.frame == key), None)

                if entry:
                    entry.count += 1
                    marker_basis = min(int(marker_basis * 1.1), 100)
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)


                if entry.count >= 10:
                    bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
                else:
                    scene["marker_min"] = int(marker_basis * 0.9)
                    scene["marker_max"] = int(marker_basis * 1.1)
                    bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')

                self._step = 0  # Wiederhole Zyklus
            else:
                bpy.ops.clip.clean_error_tracks('INVOKE_DEFAULT', verbose=True)
                self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            clip = context.space_data.clip
            marker_basis = scene.get("marker_basis", 20)

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                self._step = 1
            else:
                context.window_manager.event_timer_remove(self._timer)
                bpy.ops.clip.clean_short_tracks(action='DELETE_TRACK')
                self.report({'INFO'}, "Tracking + Markerprüfung abgeschlossen.")
                return {'FINISHED'}

            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}
