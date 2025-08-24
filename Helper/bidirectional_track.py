# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/bidirectional_track.py

Bidirektionales Tracking (sichtbar im UI) mit nachgelagerter Join-Phase,
die an Helper/triplet_joiner.py delegiert ist. Die Triplet-Gruppen müssen
vorher in der Szene persistiert worden sein (z. B. durch Helper/triplet_grouping.py
oder einen Post-Schritt in detect.py).

Features
--------
- Modal-Operator startet Vorwärts- und Rückwärts-Tracking (sequence=True).
- Stabilitätsdetektion über Marker-/Frame-Konstanz.
- Robuste CLIP_EDITOR-Kontext-Findung (temp_override) für bpy.ops.clip.*.
- Delegierter Triplet-Join via Helper/triplet_joiner.run_triplet_join(...).
- Optionaler Clean-Short (falls Modul vorhanden).
- Orchestrator-Handshake via scene["bidi_active"], scene["bidi_result"].
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import bpy
from bpy.types import Operator


# ---------------------------------------------------------------------------
# UI/Context-Utilities
# ---------------------------------------------------------------------------

def _find_clip_context() -> Tuple[Optional[bpy.types.Window],
                                  Optional[bpy.types.Area],
                                  Optional[bpy.types.Region],
                                  Optional[bpy.types.Space]]:
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for win in wm.windows:
        scr = win.screen
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'CLIP_EDITOR':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return win, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    win, area, region, space = _find_clip_context()
    if not (win and area and region and space):
        # Fallback: ohne Override ausführen (funktioniert oft trotzdem)
        return op_callable(**kwargs)
    override = {
        "window": win,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _get_active_clip_fallback() -> Optional[bpy.types.MovieClip]:
    """Versucht, einen aktiven Clip zu finden – erst UI, dann bpy.data.movieclips."""
    # 1) Aus aktivem CLIP_EDITOR
    _, _, _, space = _find_clip_context()
    if space:
        clip = getattr(space, "clip", None)
        if clip:
            return clip
    # 2) Erstbesten Clip aus Datenbank
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Marker/Track-Utilities
# ---------------------------------------------------------------------------

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


def _deselect_all_tracks(clip) -> None:
    try:
        for t in clip.tracking.tracks:
            t.select = False
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

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

    # ---------------------------------------------------------------------

    def _dbg_header(self, context, clip):
        curf = context.scene.frame_current
        total = _count_total_markers(clip) if clip else -1
        on_cur = _count_tracks_with_marker_on_frame(clip, curf) if clip else -1
        print(
            "[BidiTrack] tick=%d | step=%d | t=%.3fs | frame=%d | "
            "markers_total=%d | tracks@frame=%d"
            % (self._tick, self._step, time.perf_counter() - self._t0, int(curf), int(total), int(on_cur))
        )

    # ---------------------------------------------------------------------

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
        # 0.5 s Timer – UI-sichtbarer Pulsschlag
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        # Erste Umgebungsausgabe
        clip = _get_active_clip_fallback()
        total = _count_total_markers(clip) if clip else -1
        on_start = _count_tracks_with_marker_on_frame(clip, self._start_frame) if clip else -1
        print("[Tracking] Schritt: 0 (Start Bidirectional Track)")
        print(
            "[BidiTrack] INIT | start_frame=%d | markers_total=%d | tracks@start=%d"
            % (int(self._start_frame), int(total), int(on_start))
        )
        return {'RUNNING_MODAL'}

    # ---------------------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1
            print("[BidiTrack] TIMER tick=%d (dt=%.3fs seit Start)"
                  % (self._tick, time.perf_counter() - self._t0))
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    # ---------------------------------------------------------------------

    def run_tracking_step(self, context):
        clip = _get_active_clip_fallback()
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
                # sequence=True: vollständiger Vorwärtslauf
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
            # Zurück auf Startframe
            context.scene.frame_current = self._start_frame
            self._step = 2
            print(f"← Frame zurückgesetzt auf {self._start_frame}")
            return {'PASS_THROUGH'}

        elif self._step == 2:
            # Ein „Zwischen-Tick“ als sichtbarer Puffer
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

    # ---------------------------------------------------------------------

    def run_tracking_stability_check(self, context, clip):
        # Aktuelle Zahlen
        current_frame = context.scene.frame_current
        current_marker_count = _count_total_markers(clip)
        tracks_on_cur = _count_tracks_with_marker_on_frame(clip, current_frame)

        # Stabilitätsprüfung
        if (self._prev_marker_count == current_marker_count and
                self._prev_frame == current_frame):
            self._stable_count += 1
        else:
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

        # UI-Pulse
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass

        if self._stable_count >= 2:
            print("✓ Tracking stabil erkannt – gebe Fertig-Signal an Orchestrator.")
            return self._finish(context, result="FINISHED")

        # Zusatzhinweis
        if self._stable_count == 0:
            dt = time.perf_counter() - self._t_last_action
            if dt > 1.5:
                print(f"[BidiTrack] Hinweis: Seit {dt:.2f}s keine Stabilität. "
                      "Operatoren evtl. noch busy oder keine Markerbewegung messbar.")

        return {'PASS_THROUGH'}

    # ---------------------------------------------------------------------

    def _finish(self, context, result="FINISHED"):
        """
        Abschlussroutine:
        1) Timer/Cleanup
        2) Triplet-Join via Helper/triplet_joiner.run_triplet_join()
        3) Optionaler Clean-Short
        4) Orchestrator-Flags setzen & beenden
        """
        total_time = time.perf_counter() - self._t0
        print(f"[BidiTrack] FINISH (pre) result={result} | total_time={total_time:.3f}s | ticks={self._tick}")

        # 1) Timer-Cleanup zuerst stoppen (keine weiteren TIMER-Events)
        self._cleanup_timer(context)

        # 2) Triplet-Gruppen zusammenführen (delegiert)
        try:
            clip = _get_active_clip_fallback()
            if clip:
                try:
                    from . import triplet_joiner
                except Exception as imp_ex:
                    print(f"[BidiTrack] WARN: triplet_joiner nicht verfügbar: {imp_ex}")
                else:
                    res = triplet_joiner.run_triplet_join(context, active_policy="first")
                    print(f"[BidiTrack] Post-Join abgeschlossen | groups_joined={res.get('joined', 0)} "
                          f"| total={res.get('total', 0)} | skipped={res.get('skipped', 0)}")
            else:
                print("[BidiTrack] WARN: Kein Clip im Kontext – Join übersprungen.")
        except Exception as ex:
            print(f"[BidiTrack] WARN: Join-Phase fehlgeschlagen: {ex}")

        # 3) Nacharbeit: Clean Short Tracks (wenn verfügbar)
        try:
            from . import clean_short_tracks
            if hasattr(clean_short_tracks, "clean_short_tracks"):
                print("[BidiTrack] Starte Clean-Short-Tracks nach Bidirectional Tracking …")
                clean_short_tracks.clean_short_tracks(context)
        except Exception as ex:
            print(f"[BidiTrack] WARN: Clean-Short-Tracks konnte nicht ausgeführt werden: {ex}")

        # 4) Orchestrator-Flags zuletzt setzen
        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = str(result)
        print(f"[BidiTrack] FINISH (post) result={result}")

        return {'FINISHED'}

    # ---------------------------------------------------------------------

    def _cleanup_timer(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None


# ---------------------------------------------------------------------------
# Convenience-API
# ---------------------------------------------------------------------------

def run_bidirectional_track(context):
    """Startet den Operator aus Skript-Kontext."""
    return bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')


# ---------------------------------------------------------------------------
# Registrierung für Haupt-__init__.py
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
