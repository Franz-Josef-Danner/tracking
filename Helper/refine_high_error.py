# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import time
from math import isfinite, ceil, ceil
from typing import List, Optional

import bpy
from bpy.types import Context, Operator


# ------------------------- Kontext & Mapping ---------------------------------


def _find_clip_area_ctx(context: Context) -> Optional[dict]:
    win = context.window
    scr = win.screen if win else None
    if not win or not scr:
        return None
    area = next((a for a in scr.areas if a.type == "CLIP_EDITOR"), None)
    if not area:
        return None
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    space = area.spaces.active if area.spaces and area.spaces.active.type == "CLIP_EDITOR" else None
    ctx = dict(window=win, screen=scr, area=area, region=region)
    if space:
        ctx["space_data"] = space
        if getattr(space, "clip", None):
            ctx["edit_movieclip"] = space.clip
    return ctx


def _scene_to_clip_frame(context: Context, clip: bpy.types.MovieClip, scene_frame: int) -> int:
    scn = context.scene
    scene_start = int(getattr(scn, "frame_start", 1))
    clip_start = int(getattr(clip, "frame_start", 1))
    scn_fps = float(getattr(getattr(scn, "render", None), "fps", 0) or 0.0)
    clip_fps = float(getattr(clip, "fps", 0) or 0.0)
    scale = (clip_fps / scn_fps) if (scn_fps > 0.0 and clip_fps > 0.0) else 1.0
    rel = round((scene_frame - scene_start) * scale)
    f = int(clip_start + rel)
    dur = int(getattr(clip, "frame_duration", 0) or 0)
    if dur > 0:
        fmin, fmax = clip_start, clip_start + dur - 1
        f = max(fmin, min(f, fmax))
    return f


def _force_visible_playhead(context: Context, ovr: dict, clip: bpy.types.MovieClip,
                            scene_frame: int, *, sleep_s: float = 0.04) -> None:
    # 1) Szene-Frame
    context.scene.frame_set(int(scene_frame))
    # 2) Clip-User-Frame synchronisieren
    try:
        cf = _scene_to_clip_frame(context, clip, int(scene_frame))
        space = ovr.get("space_data", None)
        if space and getattr(space, "clip_user", None):
            space.clip_user.frame_current = int(cf)
    except Exception:
        pass
    # 3) View-Layer & Redraw
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    try:
        area = ovr.get("area", None)
        if area:
            area.tag_redraw()
        with context.temp_override(**ovr):
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass
    # 4) kleine Atempause für die UI
    if sleep_s > 0.0:
        try:
            time.sleep(float(sleep_s))
        except Exception:
            pass


# ------------------------- Marker/Track Helpers ------------------------------


def _marker_on_clip_frame(track, frame_clip: int):
    try:
        return track.markers.find_frame(frame_clip, exact=False)
    except Exception:
        return None


def _iter_tracks_with_marker_at_clip_frame(tracks, frame_clip: int):
    for tr in tracks:
        if hasattr(tr, "enabled") and not bool(getattr(tr, "enabled")):
            continue
        mk = _marker_on_clip_frame(tr, frame_clip)
        if mk is None:
            continue
        if hasattr(mk, "mute") and bool(getattr(mk, "mute")):
            continue
        yield tr


def _marker_error_on_clip_frame(track, frame_clip: int):
    try:
        mk = _marker_on_clip_frame(track, frame_clip)
        if mk is not None and hasattr(mk, "error"):
            v = float(mk.error)
            if isfinite(v):
                return v
    except Exception:
        pass
    try:
        v = float(getattr(track, "average_error"))
        return v if isfinite(v) else None
    except Exception:
        return None


def _set_selection_for_tracks_on_clip_frame(tob, frame_clip: int, tracks_subset):
    # clear
    for t in tob.tracks:
        try:
            t.select = False
            for m in t.markers:
                m.select = False
        except Exception:
            pass
    # set
    for t in tracks_subset:
        try:
            mk = _marker_on_clip_frame(t, frame_clip)
            if mk is None:
                continue
            t.select = True
            mk.select = True
        except Exception:
            pass


# ------------------------- Modal Operator (2-Phasen) -------------------------


class CLIP_OT_refine_high_error_modal(Operator):
    """Scannt alle Frames, vergleicht Fehler-Summen gegen den Solve-Error und refin’t nur dort, wo Frame-Fehler > Solve-Error ist."""
    bl_idname = "clip.refine_high_error_modal"
    bl_label = "Refine Highest Error Frames (Modal)"
    bl_options = {"REGISTER", "INTERNAL"}

    # (Kompatibilität – wird nicht genutzt)
    error_track: bpy.props.FloatProperty(default=2.0)  # type: ignore

    # Neue/angepasste Parameter
    top_n_frames: bpy.props.IntProperty(default=20, min=1)  # type: ignore
    only_selected_tracks: bpy.props.BoolProperty(default=False)  # type: ignore
    wait_seconds: bpy.props.FloatProperty(default=0.05, min=0.0, soft_max=0.5)  # type: ignore
    ui_sleep_s: bpy.props.FloatProperty(default=0.04, min=0.0, soft_max=0.2)  # type: ignore
    max_refine_calls: bpy.props.IntProperty(default=20, min=1)  # type: ignore
    tracking_object_name: bpy.props.StringProperty(default="")  # type: ignore

    # intern
    _timer: Optional[bpy.types.Timer] = None
    _ovr: Optional[dict] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _tob = None
    _tracks: List = []
    _frame_scene: int = 0
    _frame_end: int = 0
    _ops_left: int = 0

    # 2-Phasen-Steuerung
    _phase: str = "scan"  # "scan" -> "refine"
    _scan_errors: dict[int, float] = {}         # scene_frame -> error_sum
    _targets: List[int] = []                    # scene_frames (Top-N)
    _target_index: int = 0
    _solve_error: float = 0.0                   # Untergrenze aus aktueller Reconstruction

    def invoke(self, context: Context, event):
        # Kontext/Clip ermitteln
        self._ovr = _find_clip_area_ctx(context)
        if not self._ovr:
            self.report({"ERROR"}, "Kein Movie Clip Editor im aktuellen Screen")
            return {"CANCELLED"}
        self._clip = self._ovr.get("edit_movieclip") or getattr(self._ovr.get("space_data"), "clip", None)
        if not self._clip:
            self.report({"ERROR"}, "Kein Movie Clip aktiv")
            return {"CANCELLED"}

        tracking = self._clip.tracking

        # Tracking-Objekt bestimmen (vor Reconstruction-Check!)
        self._tob = (tracking.objects.get(self.tracking_object_name)
                     if self.tracking_object_name else tracking.objects.active)
        if self._tob is None:
            self.report({"ERROR"}, "Kein Tracking-Objekt aktiv")
            return {"CANCELLED"}

        # Reconstruction auf dem aktiven Tracking-Objekt prüfen und Solve-Error holen
        recon = getattr(self._tob, "reconstruction", None)
        if not recon or not getattr(recon, "is_valid", False):
            self.report({"ERROR"}, "Rekonstruktion ist nicht gültig. Erst solve durchführen.")
            return {"CANCELLED"}
        try:
            se = float(getattr(recon, "average_error", 0.0) or 0.0)
            self._solve_error = se if isfinite(se) and se >= 0.0 else 0.0
        except Exception:
            self._solve_error = 0.0

        # Track-Menge festlegen (ggf. nur selektierte)
        self._tracks = list(self._tob.tracks)
        if self.only_selected_tracks:
            self._tracks = [t for t in self._tracks if getattr(t, "select", False)]
        if not self._tracks:
            self.report({"WARNING"}, "Keine passenden Tracks gefunden")
            return {"CANCELLED"}

        scn = context.scene
        self._frame_scene = int(scn.frame_start)
        self._frame_end = int(scn.frame_end)
        self._ops_left = int(self.max_refine_calls)

        # Phasen-Init
        self._phase = "scan"
        self._scan_errors = {}
        self._targets = []
        self._target_index = 0

        # Flag: läuft
        scn["refine_active"] = True

        # Timer
        step = max(0.01, min(0.2, float(self.wait_seconds) * 0.5))
        self._timer = context.window_manager.event_timer_add(step, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        try:
            if self._phase == "scan":
                if self._frame_scene > self._frame_end:
                    # Scan abgeschlossen -> Ziele bestimmen
                    self._prepare_targets_after_scan(context)
                    if not self._targets:
                        # nichts zu tun
                        return self._finish(context, cancelled=False)
                    # Refine-Phase starten
                    self._phase = "refine"
                    self._target_index = 0
                    return {"RUNNING_MODAL"}

                # --- Scan-Schritt: Fehler-Summe für aktuellen Szenen-Frame ---
                f_scene = self._frame_scene
                f_clip = _scene_to_clip_frame(context, self._clip, f_scene)
                err_sum = 0.0
                found = False

                for tr in _iter_tracks_with_marker_at_clip_frame(self._tracks, f_clip):
                    v = _marker_error_on_clip_frame(tr, f_clip)
                    if v is not None:
                        err_sum += float(v)
                        found = True

                self._scan_errors[f_scene] = (err_sum if found else 0.0)

                # nächster Frame
                self._frame_scene += 1
                return {"RUNNING_MODAL"}

            # -------- Refine-Phase --------
            if self._ops_left <= 0 or self._target_index >= len(self._targets):
                return self._finish(context, cancelled=False)

            f_scene = int(self._targets[self._target_index])
            f_clip = _scene_to_clip_frame(context, self._clip, f_scene)
            active_tracks = list(_iter_tracks_with_marker_at_clip_frame(self._tracks, f_clip))

            if active_tracks:
                # Playhead zeigen
                _force_visible_playhead(context, self._ovr, self._clip, f_scene,
                                        sleep_s=float(self.ui_sleep_s))

                # Auswahl setzen (nur Marker dieses Frames)
                _set_selection_for_tracks_on_clip_frame(self._tob, f_clip, active_tracks)

                # refine vorwärts
                if self._ops_left > 0:
                    with context.temp_override(**self._ovr):
                        bpy.ops.clip.refine_markers("EXEC_DEFAULT", backwards=False)
                    self._ops_left -= 1
                    with context.temp_override(**self._ovr):
                        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)

                # refine rückwärts (wenn Budget)
                if self._ops_left > 0:
                    if float(self.wait_seconds) > 0.0:
                        time.sleep(min(0.2, float(self.wait_seconds)))
                    with context.temp_override(**self._ovr):
                        bpy.ops.clip.refine_markers("EXEC_DEFAULT", backwards=True)
                    self._ops_left -= 1
                    with context.temp_override(**self._ovr):
                        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)

            # nächstes Ziel
            self._target_index += 1
            return {"RUNNING_MODAL"}

        except Exception as ex:
            print(f"[RefineModal] Error: {ex!r}")
            return self._finish(context, cancelled=True)

    # Hilfsfunktion: Ziele bestimmen (Solve-Error als Untergrenze + Mindestabstand)
    def _prepare_targets_after_scan(self, context: Context) -> None:
        # Sortiere Szene-Frames nach Fehler-Summe absteigend
        pairs = sorted(self._scan_errors.items(), key=lambda kv: kv[1], reverse=True)
        thr = float(self._solve_error or 0.0)

        # Primär: nur Frames, deren kumulierter Fehler > Solve-Error ist
        filtered = [(f, s) for (f, s) in pairs if s > thr]
        if not filtered:
            filtered = [(f, s) for (f, s) in pairs if s > 0.0]
        if not filtered:
            filtered = pairs

        # Mindestabstand: frames_track / 2 (aufgerundet, mind. 1)
        try:
            frames_track = int(getattr(context.scene, "frames_track", 25) or 25)
        except Exception:
            frames_track = 25
  min_gap = max(1, int(ceil(frames_track / 2))) / 2)))

        selected: List[int] = []
        for f, _s in filtered:
            if not selected:
                selected.append(int(f))
            else:
                # Abstand gegen alle bereits gewählten Frames prüfen
                if all(abs(int(f) - g) >= min_gap for g in selected):
                    selected.append(int(f))
            if len(selected) >= int(self.top_n_frames):
                break

        self._targets = selected
        print(f"[RefineModal] Solve-Error={thr:.6f}; min_gap={min_gap}; selected {len(self._targets)}/{len(pairs)} frames")

    def _finish(self, context: Context, *, cancelled: bool):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        try:
            context.scene["refine_active"] = False
        except Exception:
            pass
        print(f"[RefineModal] DONE ({'CANCELLED' if cancelled else 'FINISHED'})")
        return {"CANCELLED" if cancelled else "FINISHED"}


# ------------------------- Public API ----------------------------------------


def start_refine_modal(
    context: Context,
    *,
    error_track: float = 2.0,  # (Kompatibilität – intern ungenutzt)
    top_n_frames: int = 20,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.05,
    ui_sleep_s: float = 0.04,
    max_refine_calls: int = 20,
    tracking_object_name: str | None = None,
) -> dict:
    """
    Startet den 2-Phasen-Modal-Operator:
      1) Scan aller Frames, Ermittlung des kumulierten Fehlerwertes pro Frame
      2) Auswahl der Frames, deren kumulierter Fehler > Solve-Error liegt (Untergrenze),
         sortiert nach Fehler und auf top_n_frames begrenzt; dann Refine (vorwärts + rückwärts)
    Rückgabe: {'status': 'STARTED'|'BUSY'|'FAILED'}.
    """
    scn = context.scene
    if scn.get("refine_active"):
        return {"status": "BUSY"}

    ovr = _find_clip_area_ctx(context)
    if not ovr:
        return {"status": "FAILED", "reason": "no_clip_editor"}

    kwargs = dict(
        error_track=float(error_track),  # ungenutzt, aber kompatibel zur Signatur
        top_n_frames=int(top_n_frames),
        only_selected_tracks=bool(only_selected_tracks),
        wait_seconds=float(wait_seconds),
        ui_sleep_s=float(ui_sleep_s),
        max_refine_calls=int(max_refine_calls),
        tracking_object_name=str(tracking_object_name or ""),
    )
    with context.temp_override(**ovr):
        bpy.ops.clip.refine_high_error_modal("INVOKE_DEFAULT", **kwargs)
    return {"status": "STARTED", **kwargs}
