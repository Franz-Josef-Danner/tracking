import time
import json
import bpy
from bpy.types import Operator
from typing import List, Dict, Any, Optional, Tuple

# Scene keys für Triplet-Gruppen (müssen zu Helper/detect.py passen)
_TRIPLET_NAMES_KEY = "pattern_triplet_groups_json"
_TRIPLET_PTRS_KEY = "pattern_triplet_groups_ptr_json"
_TRIPLET_COUNT_KEY = "pattern_triplet_groups_count"


# ---------- UI/Context-Utilities ----------

def _find_clip_context() -> Tuple[Optional[bpy.types.Window], Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
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


# ---------- Marker/Track-Utilities ----------

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


def _track_by_ptr_or_name(clip, ptr: Optional[int], name: Optional[str]):
    """Robuste Track-Auflösung: bevorzugt Pointer, sonst Name."""
    tracks = getattr(getattr(clip, "tracking", None), "tracks", [])
    # Pointer
    if ptr is not None:
        for t in tracks:
            try:
                if int(t.as_pointer()) == int(ptr):
                    return t
            except Exception:
                pass
    # Name Fallback
    if name:
        for t in tracks:
            try:
                if t.name == name:
                    return t
            except Exception:
                pass
    return None


def _load_triplet_groups_from_scene(scene) -> List[List[Dict[str, Any]]]:
    """
    Lädt Triplet-Gruppen aus Scene-Props. Form:
      - scene[_TRIPLET_PTRS_KEY] = JSON [[ptr1,ptr2,ptr3], ...]
      - scene[_TRIPLET_NAMES_KEY] = JSON [[n1,n2,n3], ...]
    Gibt Liste von Dicts je Track zurück: {"ptr": int|None, "name": str|None}
    """
    groups: List[List[Dict[str, Any]]] = []
    try:
        ptr_json = scene.get(_TRIPLET_PTRS_KEY)
        name_json = scene.get(_TRIPLET_NAMES_KEY)

        ptr_groups = json.loads(ptr_json) if isinstance(ptr_json, str) else []
        name_groups = json.loads(name_json) if isinstance(name_json, str) else []

        # Normalisieren auf gleiche Länge
        L = max(len(ptr_groups), len(name_groups))
        for idx in range(L):
            ptr_trip = ptr_groups[idx] if idx < len(ptr_groups) else []
            name_trip = name_groups[idx] if idx < len(name_groups) else []
            # Auf Länge 3 polstern
            while len(ptr_trip) < 3:
                ptr_trip.append(None)
            while len(name_trip) < 3:
                name_trip.append(None)

            trip: List[Dict[str, Any]] = [
                {"ptr": ptr_trip[0], "name": name_trip[0]},
                {"ptr": ptr_trip[1], "name": name_trip[1]},
                {"ptr": ptr_trip[2], "name": name_trip[2]},
            ]
            groups.append(trip)
    except Exception as ex:
        print(f"[BidiTrack] WARN: Triplet-Gruppen konnten nicht geladen werden: {ex}")
    return groups


def _join_triplet_groups(context, clip) -> int:
    """
    Kernfunktion: Nimmt gespeicherte 3er-Gruppen aus der Szene,
    selektiert pro Gruppe die drei Tracks und ruft bpy.ops.clip.join_tracks().
    Returns: Anzahl erfolgreich verarbeiteter Join-Operationen.
    """
    scene = context.scene
    groups = _load_triplet_groups_from_scene(scene)
    if not groups:
        print("[BidiTrack] Info: Keine Triplet-Gruppen auf Szene gefunden – kein Join notwendig.")
        return 0

    joined_ops = 0
    for g_idx, trip in enumerate(groups, start=1):
        # Tracks auflösen (Pointer bevorzugt, Name Fallback)
        tr_objs = []
        for item in trip:
            tr = _track_by_ptr_or_name(clip, item.get("ptr"), item.get("name"))
            if tr:
                tr_objs.append(tr)

        if len(tr_objs) < 3:
            print(f"[BidiTrack] Gruppe #{g_idx}: <3 gültige Tracks aufgelöst – überspringe.")
            continue

        # Selektion vorbereiten
        _deselect_all_tracks(clip)
        for t in tr_objs:
            try:
                t.select = True
            except Exception:
                pass

        # Operator ausführen (im CLIP-Kontext)
        def _op_join(**kw):
            return bpy.ops.clip.join_tracks(**kw)

        try:
            ret = _run_in_clip_context(_op_join)
            print(f"[BidiTrack] Gruppe #{g_idx}: join_tracks() -> {ret}")
            joined_ops += 1
        except Exception as ex:
            print(f"[BidiTrack] Gruppe #{g_idx}: join_tracks() Fehlgeschlagen: {ex}")

        # UI-Refresh
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

    # Selektion aufräumen
    _deselect_all_tracks(clip)
    print(f"[BidiTrack] Join-Zusammenfassung: {joined_ops}/{len(groups)} Gruppen zusammengeführt.")
    return joined_ops


# ---------- Operator ----------

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

    def _finish(self, context, result="FINISHED"):
        """
        Abschlussroutine:
        1) Timer/Cleanup
        2) Triplet-Gruppen joinen (bpy.ops.clip.join_tracks)
        3) Optionaler Clean-Short
        4) Orchestrator-Flags setzen & beenden
        """
        total_time = time.perf_counter() - self._t0
        print(f"[BidiTrack] FINISH (pre) result={result} | total_time={total_time:.3f}s | ticks={self._tick}")

        # 1) Timer-Cleanup zuerst stoppen (keine weiteren TIMER-Events)
        self._cleanup_timer(context)

        # 2) Triplet-Gruppen zusammenführen (Join)
        try:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None) if space else None
            if clip:
                joined = _join_triplet_groups(context, clip)
                print(f"[BidiTrack] Post-Join abgeschlossen | groups_joined={joined}")
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