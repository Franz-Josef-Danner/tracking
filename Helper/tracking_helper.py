# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – **modal wartend** (funktionaler Helper)

- Startet die **Funktions**-Variante `track_to_scene_end_fn(..., use_invoke=True)`.
- **Wartet modal** auf das WM‑Token, das der Helper **erst nach finalem
  Playhead‑Reset & Viewer‑Redraw** setzt.
- Meldet danach erst "Finish" (inkl. Info‑Log start → tracked_until).
"""
from __future__ import annotations

from time import time_ns, monotonic
from typing import Optional, Set

import bpy

# Funktions‑Helper + Redraw aus dem Helper‑Modul
from ..Helper.tracking_helper import track_to_scene_end_fn, _redraw_clip_editors  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

TIMEOUT_SEC = 60.0


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (wait until viewer reset)"
    bl_description = (
        "Startet track_to_scene_end_fn (Forward, Sequence, INVOKE) und wartet auf das Helper-Feedback,"
        " nachdem der Viewer aktualisiert wurde."
    )
    bl_options = {"REGISTER"}

    _token: Optional[str] = None
    _timer: Optional[object] = None
    _deadline: Optional[float] = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        wm = context.window_manager

        # 1) Token vorbereiten & Slot leeren
        self._token = str(time_ns())
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass

        # 2) Helper starten (funktional, INVOKE, setzt Token **später** im Timer)
        try:
            track_to_scene_end_fn(context, coord_token=self._token, use_invoke=True)
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Fehler: {ex}")
            return {"CANCELLED"}

        # 3) Modal warten bis Token gesetzt (nach finalem Viewer-Reset)
        self._deadline = monotonic() + TIMEOUT_SEC
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        if event.type == 'ESC':
            return self._finish(context, cancelled=True, msg="Abgebrochen (ESC)")

        if event.type == 'TIMER':
            if self._deadline is not None and monotonic() > self._deadline:
                return self._finish(context, cancelled=True, msg="Timeout (kein Feedback vom Helper)")

            wm = context.window_manager
            done = wm.get("bw_tracking_done_token", "")
            if done and self._token and done == self._token:
                # Letzter Sicherheitsschub: Viewer redraw
                try:
                    _redraw_clip_editors(context)
                except Exception:
                    pass
                info = wm.get("bw_tracking_last_info")
                if info:
                    self.report({'INFO'}, f"Tracking done: start={info.get('start_frame')} → {info.get('tracked_until')}")
                return self._finish(context, cancelled=False, msg="Finish")
        return {"RUNNING_MODAL"}

    def _finish(self, context: bpy.types.Context, *, cancelled: bool, msg: str) -> Set[str]:
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        self._deadline = None
        self._token = None
        if cancelled:
            self.report({'WARNING'}, msg)
            return {"CANCELLED"}
        else:
            self.report({'INFO'}, msg)
            return {"FINISHED"}


# ----------
# Register
# ----------
_classes = (CLIP_OT_tracking_coordinator,)


def register():
    for c in _classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass
    print("[Coordinator] registered (modal wait for viewer reset)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")
                        if reg.type in {'WINDOW', 'UI'}:
                            try:
                                reg.tag_redraw()
                            except Exception:
                                pass
        # Zusatz: einmalig global redraw anstoßen
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Intern: Playhead nach INVOKE zuverlässig zurücksetzen (Timer)
# ---------------------------------------------------------------------------

def _schedule_playhead_restore(context: bpy.types.Context, target_frame: int,
                               *, interval: float = 0.10,
                               settle_ticks: int = 2,
                               enforce_ticks: int = 6,
                               wm: Optional[bpy.types.WindowManager] = None,
                               coord_token: str = "",
                               info_ref: Optional[dict] = None) -> None:
    """Nachbildung der *bidirectional* Logik mit Stabilitätsprüfung.

    Stabil gilt nur, wenn **sowohl** `frame_current` als auch die **Marker-Anzahl**
    (Summe über alle Tracks) sich `settle_ticks` Zyklen **nicht** verändert haben.
    Danach wird der Playhead auf `target_frame` gesetzt und für `enforce_ticks`
    Zyklen „festgenagelt“. Erst **danach** wird ein optionales Token gesetzt.
    """
    state = {"last_frame": None, "last_count": None, "stable": 0,
             "phase": "settle", "enforce": 0, "max_frame": int(target_frame)}
    _log(f"Timer registrieren (bidir-like): target={target_frame}, interval={interval}s, settle={settle_ticks}, enforce={enforce_ticks}")

    def _marker_count() -> int:
        handles = _clip_editor_handles(context)
        if not handles:
            return -1
        space = handles.get("space_data")
        clip = getattr(space, "clip", None) if space else None
        if clip is None:
            return -1
        try:
            return sum(len(t.markers) for t in clip.tracking.tracks)
        except Exception:
            return -1

    def _poll():
        sc = context.scene
        if sc is None:
            _log("Timer: kein Scene-Kontext – stop")
            return None

        cur_frame = int(sc.frame_current)
        cur_count = _marker_count()
        if cur_frame > state["max_frame"]:
            state["max_frame"] = cur_frame

        # --- settle-Phase: auf Stabilität warten (Frame & Markerzahl) ---
        if state["phase"] == "settle":
            same = (state["last_frame"] == cur_frame) and (state["last_count"] == cur_count)
            state["stable"] = state["stable"] + 1 if same else 0
            state["last_frame"], state["last_count"] = cur_frame, cur_count
            _log(f"Timer/settle: frame={cur_frame}, count={cur_count}, stable={state['stable']}")
            if state["stable"] >= settle_ticks:
                try:
                    sc.frame_set(target_frame)
                    _redraw_clip_editors(context)
                    _log(f"Timer/settle: setze Frame -> {target_frame} + redraw")
                except Exception as ex:
                    _log(f"Timer/settle: frame_set Fehler: {ex}")
                state["phase"] = "enforce"
                state["enforce"] = 0
            return interval

        # --- enforce-Phase: eine Weile auf target halten ---
        if cur_frame != target_frame:
            try:
                sc.frame_set(target_frame)
                _redraw_clip_editors(context)
                _log(f"Timer/enforce: korrigiere {cur_frame} -> {target_frame} + redraw")
            except Exception as ex:
                _log(f"Timer/enforce: frame_set Fehler: {ex}")
            state["enforce"] = 0
        else:
            state["enforce"] += 1
            _log(f"Timer/enforce: ok (cur={cur_frame}), ok_ticks={state['enforce']}")

        if state["enforce"] >= enforce_ticks:
            # Finale Aktualisierung + optional Token setzen
            if info_ref is not None:
                try:
                    info_ref["tracked_until"] = state["max_frame"]
                    _log(f"Timer: final tracked_until={state['max_frame']}")
                    if wm is not None:
                        wm["bw_tracking_last_info"] = info_ref
                except Exception:
                    pass
            if wm is not None and coord_token:
                try:
                    wm["bw_tracking_done_token"] = coord_token
                    _log(f"Timer: Token gesetzt -> {coord_token}")
                except Exception as ex:
                    _log(f"Timer: Token-Set Fehler: {ex}")
            _log("Timer: fertig – entferne Timer")
            return None
        return interval

    try:
        bpy.app.timers.register(_poll, first_interval=interval)
    except Exception as ex:
        _log(f"Timer-Registrierung fehlgeschlagen: {ex} – setze sofort target & Token")
        try:
            context.scene.frame_set(target_frame)
        except Exception as ex2:
            _log(f"Fallback frame_set Fehler: {ex2}")
        if wm is not None and coord_token:
            try:
                wm["bw_tracking_done_token"] = coord_token
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Public API: Playhead merken/zurücksetzen
# ---------------------------------------------------------------------------

@contextmanager
def remember_playhead(context: bpy.types.Context) -> Iterator[int]:
    """Merkt den aktuellen Scene-Frame und setzt ihn beim Verlassen zurück."""
    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")
    start_frame = int(scene.frame_current)
    _log(f"remember_playhead: merke start_frame={start_frame}")
    try:
        yield start_frame
    finally:
        try:
            scene.frame_set(start_frame)
            _redraw_clip_editors(context)
            _log(f"remember_playhead: setze zurück -> {start_frame} + redraw")
        except Exception as ex:
            _log(f"remember_playhead: frame_set Fehler: {ex}")


# ---------------------------------------------------------------------------
# Public API: Funktionsbasierter Helper
# ---------------------------------------------------------------------------

def track_to_scene_end_fn(context: bpy.types.Context, *, coord_token: str = "", use_invoke: bool = True) -> Dict[str, Any]:
    """Trackt **selektierte Marker** vorwärts über die Sequenz.

    Parameters
    ----------
    context : bpy.types.Context
        Aktueller Blender-Kontext (mit offenem CLIP_EDITOR im aktiven Window).
    coord_token : str, optional
        Wenn gesetzt, schreibt der Helper das Token in
        ``context.window_manager["bw_tracking_done_token"]``.
    use_invoke : bool, default True
        True  → nutze `INVOKE_DEFAULT` (modal) + Timer-Reset
        False → nutze `EXEC_DEFAULT` (synchron) + direkten Reset

    Returns
    -------
    Dict[str, Any]
        "start_frame", "tracked_until", "scene_end", "backwards" (False), "sequence" (True), "mode"
    """
    _log(f"track_to_scene_end_fn: start (use_invoke={use_invoke})")
    handles = _clip_editor_handles(context)
    if not handles:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    scene = context.scene
    if scene is None:
        raise RuntimeError("Kein Scene-Kontext verfügbar")

    wm = context.window_manager
    end_frame = int(scene.frame_end)
    _log(f"Frames: current={int(scene.frame_current)}, scene_end={end_frame}")

    if use_invoke:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                _log("rufe bpy.ops.clip.track_markers('INVOKE_DEFAULT', fwd, seq=True) auf …")
                ret = bpy.ops.clip.track_markers(
                    'INVOKE_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
                _log(f"Operator-Return (INVOKE): {ret}")
            # Der Operator läuft modal weiter → tracked_until ermitteln wir per Timer
            tracked_until = int(context.scene.frame_current)
            _log(f"tracked_until (sofort nach Call): {tracked_until}")
        # Info-Dict anlegen, aber Token **noch nicht** setzen – das übernimmt der Timer
        info = {
            "start_frame": start_frame,
            "tracked_until": tracked_until,  # wird vom Timer auf max aktualisiert
            "scene_end": end_frame,
            "backwards": False,
            "sequence": True,
            "mode": "INVOKE",
        }
        wm["bw_tracking_last_info"] = info
        _schedule_playhead_restore(context, start_frame, wm=wm, coord_token=coord_token, info_ref=info)
    else:
        with remember_playhead(context) as start_frame:
            with context.temp_override(**handles):
                _log("rufe bpy.ops.clip.track_markers('EXEC_DEFAULT', fwd, seq=True) auf …")
                ret = bpy.ops.clip.track_markers(
                    'EXEC_DEFAULT',
                    backwards=False,
                    sequence=True,
                )
                _log(f"Operator-Return (EXEC): {ret}")
            tracked_until = int(context.scene.frame_current)
            _log(f"tracked_until (nach EXEC): {tracked_until}")

    if not use_invoke and coord_token:
        wm["bw_tracking_done_token"] = coord_token
        _log(f"WM-Token gesetzt (EXEC) -> {coord_token}")

    info = {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": end_frame,
        "backwards": False,
        "sequence": True,
        "mode": "INVOKE" if use_invoke else "EXEC",
    }
    wm["bw_tracking_last_info"] = info
    _log(f"Info geschrieben: {info}")
    _log("track_to_scene_end_fn: fertig")
    return info
