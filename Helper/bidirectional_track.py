import time
import bpy
from bpy.types import Operator


def _count_total_markers(clip) -> int:
    try:
        return sum(len(t.markers) for t in clip.tracking.tracks)
    except Exception:
        return 0


def _count_tracks_with_marker_on_frame(clip, frame: int) -> int:
    cnt = 0
    try:
        for tr in clip.tracking.tracks:
            try:
                mk = tr.markers.find_frame(frame, exact=True)
            except TypeError:
                mk = tr.markers.find_frame(frame)
            if mk and not getattr(mk, "mute", False):
                cnt += 1
    except Exception:
        pass
    return cnt


class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts (sichtbar im UI) und signalisiert Fertig an Orchestrator"

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    # Debug/Tracing
    _t0 = 0.0
    _tick = 0
    _t_last_action = 0.0

    def _dbg_header(self, context, clip):
        curf = context.scene.frame_current
        total = _count_total_markers(clip) if clip else -1
        on_cur = _count_tracks_with_marker_on_frame(clip, curf) if clip else -1
        print(
            "[BidiTrack] tick=%d | step=%d | t=%.3fs | frame=%d | "
            "markers_total=%d | tracks@frame=%d"
            % (self._tick, self._step, time.perf_counter() - self._t0, int(curf), int(total), int(on_cur))
        )

    def execute(self, context):
        # Flags für Orchestrator setzen
        context.scene["bidi_active"] = True
        context.scene["bidi_result"] = ""

        self._step = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1
        self._start_frame = context.scene.frame_current

        self._t0 = time.perf_counter()
        self._t_last_action = self._t0
        self._tick = 0

        wm = context.window_manager
        # Hinweis: 0.5 s ist dein aktuelles Intervall – nur Logging, kein Verhalten geändert
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        # Erste Umgebungsausgabe
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        total = _count_total_markers(clip) if clip else -1
        on_start = _count_tracks_with_marker_on_frame(clip, self._start_frame) if clip else -1
        print("[Tracking] Schritt: 0 (Start Bidirectional Track)")
        print(
            "[BidiTrack] INIT | start_frame=%d | markers_total=%d | tracks@start=%d"
            % (int(self._start_frame), int(total), int(on_start))
        )
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1
            # Kleiner Heartbeat pro Tick
            print("[BidiTrack] TIMER tick=%d (dt=%.3fs seit Start)"
                  % (self._tick, time.perf_counter() - self._t0))
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    def run_tracking_step(self, context):
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            print("[BidiTrack] ABORT: Kein aktiver Clip im Tracking-Editor.")
            return self._finish(context, result="FAILED")

        self._dbg_header(context, clip)

        if self._step == 0:
            # Vorwärts-Tracking starten
            print("→ Starte Vorwärts-Tracking...")
            total_before = _count_total_markers(clip)
            frames_before = _count_tracks_with_marker_on_frame(clip, context.scene.frame_current)
            try:
                ret = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            except Exception as ex:
                print(f"[BidiTrack] EXC beim Start Vorwärts-Tracking: {ex!r}")
                return self._finish(context, result="FAILED")

            print(
                f"[BidiTrack] Vorwärts-Tracking ausgelöst | op_ret={ret} | "
                f"markers_total_before={total_before} | tracks@frame_before={frames_before}"
            )
            self._t_last_action = time.perf_counter()
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            # Kurze Statusmeldung: hat sich seit dem Auslösen etwas geändert?
            total_now = _count_total_markers(clip)
            on_cur = _count_tracks_with_marker_on_frame(clip, context.scene.frame_current)
            print(
                f"→ Warte auf Abschluss des Vorwärts-Trackings... | "
                f"markers_total_now={total_now} | tracks@cur={on_cur}"
            )
            # Zurück auf Startframe – wie in deiner Version
            context.scene.frame_current = self._start_frame
            self._step = 2
            print(f"← Frame zurückgesetzt auf {self._start_frame}")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            # Ein „Zwischen‑Tick“ als sichtbarer Puffer
            print("→ Frame gesetzt. Warte eine Schleife, bevor Rückwärts-Tracking startet...")
            self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            # Rückwärts-Tracking starten
            print("→ Starte Rückwärts-Tracking...")
            total_before = _count_total_markers(clip)
            frames_before = _count_tracks_with_marker_on_frame(clip, context.scene.frame_current)
            try:
                ret = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            except Exception as ex:
                print(f"[BidiTrack] EXC beim Start Rückwärts-Tracking: {ex!r}")
                return self._finish(context, result="FAILED")

            print(
                f"[BidiTrack] Rückwärts-Tracking ausgelöst | op_ret={ret} | "
                f"markers_total_before={total_before} | tracks@frame_before={frames_before}"
            )
            self._t_last_action = time.perf_counter()
            self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            return self.run_tracking_stability_check(context, clip)

        return {'PASS_THROUGH'}

    def run_tracking_stability_check(self, context, clip):
        # Aktuelle Zahlen
        current_frame = context.scene.frame_current
        current_marker_count = _count_total_markers(clip)
        tracks_on_cur = _count_tracks_with_marker_on_frame(clip, current_frame)

        # Stabilitätsprüfung wie gehabt
        if (self._prev_marker_count == current_marker_count and
                self._prev_frame == current_frame):
            self._stable_count += 1
        else:
            # Extra-Log um Veränderungen zu sehen
            if self._prev_marker_count != -1:
                print(
                    "[BidiTrack] Änderung erkannt | "
                    f"prev_markers={self._prev_marker_count} -> now={current_marker_count} | "
                    f"prev_frame={self._prev_frame} -> now={current_frame}"
                )
            self._stable_count = 0

        self._prev_marker_count = current_marker_count
        self._prev_frame = current_frame

        print(
            f"[Tracking-Stabilität] Frame: {current_frame}, "
            f"Marker_total: {current_marker_count}, tracks@frame: {tracks_on_cur}, "
            f"Stabil: {self._stable_count}/2"
        )

        # Kleines UI-Pulse, damit man in der Oberfläche auch Aktivität sieht
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        if self._stable_count >= 2:
            print("✓ Tracking stabil erkannt – gebe Fertig-Signal an Orchestrator.")
            return self._finish(context, result="FINISHED")

        # Zusatzhinweis, falls „nichts“ passiert
        if self._stable_count == 0:
            dt = time.perf_counter() - self._t_last_action
            if dt > 1.5:
                print(f"[BidiTrack] Hinweis: Seit {dt:.2f}s keine Stabilität. "
                      "Operatoren evtl. noch busy oder keine Markerbewegung messbar.")

        return {'PASS_THROUGH'}

    def _finish(self, context, result="FINISHED"):
        # Flags für Orchestrator setzen
        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = str(result)

        total_time = time.perf_counter() - self._t0
        print(f"[BidiTrack] FINISH result={result} | total_time={total_time:.3f}s | ticks={self._tick}")

        self._cleanup_timer(context)

        # ---- Nacharbeit: Clean Error Tracks aufrufen ----
        try:
            from . import clean_error_tracks
            if hasattr(clean_error_tracks, "run_clean_error_tracks"):
                print("[BidiTrack] Starte Clean-Error-Tracks nach Bidirectional Tracking …")
                clean_error_tracks.run_clean_error_tracks(context)
        except Exception as ex:
            print(f"[BidiTrack] WARN: Clean-Error-Tracks konnte nicht ausgeführt werden: {ex}")

        return {'FINISHED'}

    def _cleanup_timer(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


def run_bidirectional_track(context):
    """Startet den Operator aus Skript-Kontext."""
    return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')


# ---- Registrierung für Haupt-__init__.py ----
def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
