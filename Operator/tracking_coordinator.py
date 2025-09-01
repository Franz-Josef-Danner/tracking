"""tracking_coordinator.py – Streng sequentieller, MODALER Orchestrator
Phasen: FIND_LOW → JUMP → DETECT → DISTANZE → (optional MULTI) → BIDI → (zurück)
"""

from __future__ import annotations

import bpy

from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once
from ..Helper.distanze import run_distance_cleanup
from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle
from ..Helper.clean_short_segments import clean_short_segments
from ..Helper.clean_short_tracks import clean_short_tracks
from ..Helper.split_cleanup import recursive_split_cleanup
from ..Helper.find_max_marker_frame import run_find_max_marker_frame  # type: ignore
from ..Helper.solve_camera import solve_camera_only  # type: ignore
from ..Helper.reduce_error_tracks import (
    run_reduce_error_tracks,
    get_avg_reprojection_error,
)  # type: ignore
from ..Helper.tracker_settings import apply_tracker_settings
from ..Helper.marker_helper_main import marker_helper_main

# --- NEU: State-/A-Werte/Report-Integration ---
from ..Helper.tracking_state import (
    orchestrate_on_jump,
    record_bidirectional_result,
    _get_state,
    _ensure_frame_entry,
    _popup_error_report,
)

# Versuche, die Auswertungsfunktion für die Markeranzahl zu importieren.
# Diese Funktion soll nach dem Distanz-Cleanup ausgeführt werden und
# verwendet interne Grenzwerte aus der count.py. Es werden keine
# zusätzlichen Parameter übergeben.
try:
    from ..Helper.count import evaluate_marker_count  # type: ignore
except Exception:
    try:
        from .count import evaluate_marker_count  # type: ignore
    except Exception:
        evaluate_marker_count = None  # type: ignore

# Optional: den Bidirectional-Track Operator importieren.
# Wenn der Import fehlschlägt, bleibt die Variable auf None und es erfolgt kein Aufruf.
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    try:
        from .bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
    except Exception:
        CLIP_OT_bidirectional_track = None  # type: ignore

# Optionaler Multi-Pass Helper
try:
    from ..Helper.multi import run_multi_pass  # type: ignore
except Exception:
    try:
        from .multi import run_multi_pass  # type: ignore
    except Exception:
        run_multi_pass = None  # type: ignore

# Import the detect threshold key so we can reference the last used value
try:
    from ..Helper.detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
except Exception:
    try:
        from .detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
    except Exception:
        DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator",)

# --- Orchestrator-Phasen ----------------------------------------------------
PH_FIND_LOW = "FIND_LOW"
PH_JUMP = "JUMP"
PH_DETECT = "DETECT"
PH_DISTANZE = "DISTANZE"
PH_SPIKE_CYCLE = "SPIKE_CYCLE"
PH_SOLVE_EVAL = "SOLVE_EVAL"
# Erweiterte Phase: Bidirectional-Tracking.
PH_BIDI = "BIDI"

# ---- intern: State Keys / Locks -------------------------------------------
_LOCK_KEY = "tco_lock"


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def _solve_log(context, value):
    """Laufzeit-sicherer Aufruf von __init__.kaiserlich_solve_log_add()."""
    try:
        import sys
        import importlib

        root_name = (__package__ or __name__).split(".", 1)[0] or "tracking"
        mod = sys.modules.get(root_name)
        if mod and hasattr(mod, "kaiserlich_solve_log_add"):
            return getattr(mod, "kaiserlich_solve_log_add")(context, value)
        mod = importlib.import_module(root_name)
        fn = getattr(mod, "kaiserlich_solve_log_add", None)
        if callable(fn):
            return fn(context, value)
    except Exception:
        pass
    return


def _ensure_clip_context(context: bpy.types.Context) -> dict:
    """Finde einen CLIP_EDITOR und liefere ein temp_override-Dict für Clip-Operatoren."""
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return {
                    "window": win,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "scene": bpy.context.scene,
                }
    return {}


def _resolve_clip(context: bpy.types.Context):
    """Robuster Clip-Resolver (Edit-Clip, Space-Clip, erster Clip)."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


# Blender 4.4: Refine-Flag direkt in Tracking-Settings spiegeln
def _apply_refine_focal_flag(context: bpy.types.Context, flag: bool) -> None:
    try:
        clip = _resolve_clip(context)
        tr = getattr(clip, "tracking", None) if clip else None
        settings = getattr(tr, "settings", None) if tr else None
        if settings and hasattr(settings, "refine_intrinsics_focal_length"):
            settings.refine_intrinsics_focal_length = bool(flag)
            print(f"[Coordinator] refine_intrinsics_focal_length → {bool(flag)}")
        else:
            print("[Coordinator] WARN: refine_intrinsics_focal_length nicht verfügbar")
    except Exception as exc:
        print(f"[Coordinator] WARN: refine-Flag konnte nicht gesetzt werden: {exc}")


def _snapshot_track_ptrs(context: bpy.types.Context) -> list[int]:
    """Snapshot der aktuellen Track-Pointer (nur ephemer im Python-Kontext verwenden)."""
    clip = _resolve_clip(context)
    if not clip:
        return []
    try:
        return [int(t.as_pointer()) for t in clip.tracking.tracks]
    except Exception:
        return []


# --- NEU: Marker-Delta-Helfer für A_k-Berechnung ----------------------------

def _snapshot_marker_counts(context: bpy.types.Context) -> dict[str, int]:
    """Zählt Marker je selektiertem Track (als Proxy für getrackte Frames)."""
    clip = _resolve_clip(context)
    counts: dict[str, int] = {}
    if not clip:
        return counts
    for obj in clip.tracking.objects:
        for tr in obj.tracks:
            if getattr(tr, "select", False):
                counts[tr.name] = len(tr.markers)
    return counts


def _delta_marker_counts(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """Berechnet neu hinzugekommene Marker je Track: after - before (>=0)."""
    out: dict[str, int] = {}
    for name, a in after.items():
        b = before.get(name, 0)
        out[name] = max(0, int(a) - int(b))
    return out


# ----------------------------------------------------------------------------
# Bootstrap
# ----------------------------------------------------------------------------

def _bootstrap(context: bpy.types.Context) -> None:
    """Minimaler Reset + sinnvolle Defaults; Helper initialisieren."""
    scn = context.scene
    # Tracker-Settings
    try:
        scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=True))
    except Exception as exc:
        scn["tco_last_tracker_settings"] = {"status": "FAILED", "reason": str(exc)}

    # Marker-Helper
    try:
        ok, count, info = marker_helper_main(context)
        scn["tco_last_marker_helper"] = {
            "ok": bool(ok),
            "count": int(count),
            "info": dict(info) if hasattr(info, "items") else info,
        }
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}

    scn[_LOCK_KEY] = False


# --- Operator: wird vom UI-Button aufgerufen -------------------------------

class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator (Modal, strikt sequenziell)"""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # — Laufzeit-State (nur Operator, nicht Szene) —
    _timer: object | None = None
    phase: str = PH_FIND_LOW
    target_frame: int | None = None
    repeat_map: dict[int, int] = {}
    pre_ptrs: set[int] | None = None
    detection_threshold: float | None = None
    spike_threshold: float | None = None
    bidi_started: bool = False
    solve_refine_attempted: bool = False

    # NEU: Marker-Snapshots rund um Bidirectional-Tracking
    _bidi_before_counts: dict[str, int] | None = None

    def execute(self, context: bpy.types.Context):
        # Bootstrap/Reset
        try:
            _bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}

        self.report({'INFO'}, "Coordinator: Bootstrap OK")

        # Modal starten
        self.phase = PH_FIND_LOW
        self.target_frame = None
        self.repeat_map = {}
        self.pre_ptrs = None
        self.detection_threshold = None
        self.spike_threshold = None
        self.solve_refine_attempted = False
        self._bidi_before_counts = None
        self.bidi_started = False

        wm = context.window_manager

        # --- Robust: valides Window sichern ---
        win = getattr(context, "window", None)
        if not win:
            try:
                win = _ensure_clip_context(context).get("window", None)
            except Exception:
                win = None
        if not win:
            win = getattr(bpy.context, "window", None)

        try:
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
            self.report({'INFO'}, f"Timer status=OK (window={'set' if win else 'none'})")
        except Exception as exc:
            self.report({'WARNING'}, f"Timer setup failed ({exc}); retry without window")
            try:
                self._timer = wm.event_timer_add(0.10)
            except Exception as exc2:
                self.report({'ERROR'}, f"Timer hard-failed: {exc2}")
                return {'CANCELLED'}

        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, *, info: str | None = None, cancelled: bool = False):
        # Timer sauber entfernen
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        if info:
            self.report({'INFO'} if not cancelled else {'WARNING'}, info)
        return {'CANCELLED' if cancelled else 'FINISHED'}

    def modal(self, context: bpy.types.Context, event):
        # --- ESC / Abbruch prüfen ---
        if event.type in {'ESC'} and event.value == 'PRESS':
            return self._finish(context, info="ESC gedrückt – Prozess abgebrochen.", cancelled=True)

        # nur Timer-Events verarbeiten
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Optionales Debugging: erste 3 Ticks loggen
        try:
            cnt = int(getattr(self, "_dbg_tick_count", 0)) + 1
            if cnt <= 3:
                self.report({'INFO'}, f"TIMER tick #{cnt}, phase={self.phase}")
            self._dbg_tick_count = cnt
        except Exception:
            pass

        # PHASE 1: FIND_LOW
        if self.phase == PH_FIND_LOW:
            res = run_find_low_marker_frame(context)
            st = res.get("status")
            if st == "FAILED":
                return self._finish(context, info=f"FIND_LOW FAILED → {res.get('reason')}", cancelled=True)
            if st == "NONE":
                # Kein Low-Marker-Frame gefunden: Starte Spike-Zyklus
                self.phase = PH_SPIKE_CYCLE
                self.spike_threshold = 100.0
                return {'RUNNING_MODAL'}

            self.target_frame = int(res.get("frame"))
            self.report({'INFO'}, f"Low-Marker-Frame: {self.target_frame}")
            self.phase = PH_JUMP
            return {'RUNNING_MODAL'}

        # PHASE 2: JUMP
        if self.phase == PH_JUMP:
            if self.target_frame is None:
                return self._finish(context, info="JUMP: Kein Ziel-Frame gesetzt.", cancelled=True)

            rj = run_jump_to_frame(context, frame=self.target_frame, repeat_map=self.repeat_map)
            if rj.get("status") != "OK":
                return self._finish(context, info=f"JUMP FAILED → {rj}", cancelled=True)

            self.report({'INFO'}, f"Playhead gesetzt: f{rj.get('frame')} (repeat={rj.get('repeat_count')})")

            # **NEU**: Orchestrator ausführen (setzt Motion-Model / zählt count hoch / ggf. Abbruch bei 10)
            orchestrate_on_jump(context, frame=self.target_frame)

            # Nach Orchestrierung: Abbruch bei count >= 10 (Report anzeigen)
            state = _get_state(context)
            entry, _ = _ensure_frame_entry(state, self.target_frame)
            if int(entry.get("count", 1)) >= 10:
                _popup_error_report(context, self.target_frame, entry)
                return self._finish(context, info=f"Abbruch: Frame {self.target_frame} hat 10 Durchläufe.", cancelled=True)

            # **WICHTIG**: Pre-Snapshot direkt vor DETECT
            self.pre_ptrs = set(_snapshot_track_ptrs(context))

            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}

        # PHASE 3: DETECT
        if self.phase == PH_DETECT:
            _kwargs: dict[str, object] = {"start_frame": self.target_frame}
            if self.detection_threshold is not None:
                _kwargs["threshold"] = float(self.detection_threshold)

            rd = run_detect_once(context, **_kwargs)
            if rd.get("status") != "READY":
                return self._finish(context, info=f"DETECT FAILED → {rd}", cancelled=True)

            new_cnt = int(rd.get("new_tracks", 0))
            try:
                self.detection_threshold = float(rd.get("threshold", self.detection_threshold))
            except Exception:
                pass

            self.report({'INFO'}, f"DETECT @f{self.target_frame}: new={new_cnt}, thr={self.detection_threshold}")
            self.phase = PH_DISTANZE
            return {'RUNNING_MODAL'}

        # PHASE 4: DISTANZE
        if self.phase == PH_DISTANZE:
            if self.pre_ptrs is None or self.target_frame is None:
                return self._finish(context, info="DISTANZE: Pre-Snapshot oder Ziel-Frame fehlt.", cancelled=True)

            try:
                dis = run_distance_cleanup(
                    context,
                    pre_ptrs=self.pre_ptrs,
                    frame=int(self.target_frame),
                    # min_distance=None → Auto-Ableitung in distanze.py (aus Threshold & scene-base)
                    min_distance=None,
                    distance_unit="pixel",
                    require_selected_new=True,
                    include_muted_old=False,
                    select_remaining_new=True,
                    verbose=True,
                )
            except Exception as exc:
                return self._finish(context, info=f"DISTANZE FAILED → {exc}", cancelled=True)

            removed = dis.get('removed', 0)
            kept = dis.get('kept', 0)

            # NUR neue Tracks berücksichtigen, die AM target_frame einen Marker besitzen
            new_ptrs_after_cleanup: set[int] = set()
            clip = _resolve_clip(context)
            if clip and isinstance(self.pre_ptrs, set):
                trk = getattr(clip, "tracking", None)
                if trk and hasattr(trk, "tracks"):
                    for t in trk.tracks:
                        ptr = int(t.as_pointer())
                        if ptr in self.pre_ptrs:
                            continue  # nicht neu
                        try:
                            m = t.markers.find_frame(int(self.target_frame), exact=True)
                        except TypeError:
                            m = t.markers.find_frame(int(self.target_frame))
                        if m:
                            new_ptrs_after_cleanup.add(ptr)

            # Markeranzahl auswerten, sofern die Zählfunktion vorhanden ist.
            eval_res = None
            scn = context.scene
            if evaluate_marker_count is not None:
                try:
                    eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_ptrs_after_cleanup)  # type: ignore
                except Exception as exc:
                    eval_res = {"status": "ERROR", "reason": str(exc), "count": len(new_ptrs_after_cleanup)}

            try:
                scn["tco_last_marker_count"] = eval_res
            except Exception:
                pass

            status = str(eval_res.get("status", "")) if isinstance(eval_res, dict) else ""

            if status in {"TOO_FEW", "TOO_MANY"}:
                # *** Distanzé-Semantik: nur den MARKER am aktuellen Frame löschen ***
                deleted_markers = 0
                if clip and new_ptrs_after_cleanup:
                    trk = getattr(clip, "tracking", None)
                    if trk and hasattr(trk, "tracks"):
                        curf = int(self.target_frame)
                        try:
                            # Selektion vorbereiten
                            target_ptrs = set(new_ptrs_after_cleanup)
                            for t in trk.tracks:
                                try:
                                    t.select = False
                                except Exception:
                                    pass
                            for t in trk.tracks:
                                if int(t.as_pointer()) in target_ptrs:
                                    try:
                                        t.select = True
                                    except Exception:
                                        pass
                            # Frame sicher setzen
                            try:
                                scn.frame_set(curf)
                            except Exception:
                                pass
                            override = _ensure_clip_context(context)
                            if override:
                                with bpy.context.temp_override(**override):
                                    bpy.ops.clip.delete_marker(confirm=False)
                            else:
                                bpy.ops.clip.delete_marker(confirm=False)
                            deleted_markers = len(target_ptrs)
                        except Exception:
                            # Fallback: direkte API
                            for t in trk.tracks:
                                if int(t.as_pointer()) in new_ptrs_after_cleanup:
                                    while True:
                                        try:
                                            _m = None
                                            try:
                                                _m = t.markers.find_frame(curf, exact=True)
                                            except TypeError:
                                                _m = t.markers.find_frame(curf)
                                            if not _m:
                                                break
                                            t.markers.delete_frame(curf)
                                            deleted_markers += 1
                                        except Exception:
                                            break
                        # Flush/Refresh
                        try:
                            bpy.context.view_layer.update()
                            scn.frame_set(curf)
                        except Exception:
                            pass

                # Threshold neu berechnen
                try:
                    anzahl_neu = float(eval_res.get("count", 0))
                    marker_min = float(eval_res.get("min", 0))
                    marker_max = float(eval_res.get("max", 0))
                    marker_adapt = float(scn.get("marker_adapt", 0.0)) or ((marker_min + marker_max) / 2.0)
                    if marker_adapt <= 0.0:
                        marker_adapt = 1.0
                    base_thr = float(
                        self.detection_threshold if self.detection_threshold is not None
                        else scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75)
                    )
                    self.detection_threshold = max(base_thr * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                except Exception:
                    pass

                self.report(
                    {'INFO'},
                    f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, "
                    f"eval={eval_res}, thr→{self.detection_threshold}"
                )
                # Zurück zu DETECT mit neuem Threshold
                self.phase = PH_DETECT
                return {'RUNNING_MODAL'}

            # Markeranzahl im gültigen Bereich – optional Multi-Pass und dann Bidirectional-Track ausführen.
            did_multi = False
            if isinstance(eval_res, dict) and str(eval_res.get("status", "")) == "ENOUGH":
                if run_multi_pass is not None:
                    try:
                        current_ptrs = set(_snapshot_track_ptrs(context))
                        try:
                            thr = float(self.detection_threshold) if self.detection_threshold is not None else None
                        except Exception:
                            thr = None
                        if thr is None:
                            try:
                                thr = float(context.scene.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                            except Exception:
                                thr = 0.5

                        mp_res = run_multi_pass(
                            context,
                            detect_threshold=float(thr),
                            pre_ptrs=current_ptrs,
                        )
                        try:
                            context.scene["tco_last_multi_pass"] = mp_res  # type: ignore
                        except Exception:
                            pass

                        self.report(
                            {'INFO'},
                            f"MULTI-PASS ausgeführt: created_low={mp_res.get('created_low')}, "
                            f"created_high={mp_res.get('created_high')}, selected={mp_res.get('selected')}"
                        )

                        # Nach dem Multi-Pass Distanzprüfung durchführen.
                        try:
                            cur_frame = int(self.target_frame) if self.target_frame is not None else None
                            if cur_frame is not None:
                                dist_res = run_distance_cleanup(
                                    context,
                                    pre_ptrs=current_ptrs,
                                    frame=cur_frame,
                                    min_distance=None,
                                    distance_unit="pixel",
                                    require_selected_new=True,
                                    include_muted_old=False,
                                    select_remaining_new=True,
                                    verbose=True,
                                )
                                try:
                                    context.scene["tco_last_multi_distance_cleanup"] = dist_res  # type: ignore
                                except Exception:
                                    pass
                                self.report(
                                    {'INFO'},
                                    f"MULTI-PASS DISTANZE: removed={dist_res.get('removed')}, kept={dist_res.get('kept')}"
                                )
                        except Exception as exc:
                            self.report({'WARNING'}, f"Multi-Pass Distanzé-Aufruf fehlgeschlagen ({exc})")

                        did_multi = True
                    except Exception as exc:
                        self.report({'WARNING'}, f"Multi-Pass-Aufruf fehlgeschlagen ({exc})")
                else:
                    self.report({'WARNING'}, "Multi-Pass nicht verfügbar – kein Aufruf durchgeführt")

            # Wenn ein Multi-Pass ausgeführt wurde, starte nun die Bidirectional-Track-Phase.
            if did_multi:
                # **NEU**: Vorher-Snapshot für A_k-Delta
                self._bidi_before_counts = _snapshot_marker_counts(context)

                self.phase = PH_BIDI
                self.bidi_started = False
                self.report(
                    {'INFO'},
                    f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res} – Starte Bidirectional-Track"
                )
                return {'RUNNING_MODAL'}

            # In allen anderen Fällen (kein ENOUGH oder kein Multi-Pass) wird die Sequenz beendet.
            self.report(
                {'INFO'},
                f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}"
            )
            return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)

        # PHASE: SOLVE_EVAL – Solve prüfen, loggen, Retry/Reduce steuern
        if self.phase == PH_SOLVE_EVAL:
            scn = context.scene
            try:
                target_err = float(scn.get("error_track", 2.0))
            except Exception:
                target_err = 2.0

            # 1) messen & loggen
            avg_err = get_avg_reprojection_error(context)
            _solve_log(context, avg_err)

            # 2) kein Wert → Retry einmalig, sonst mind. 1 Track löschen
            if avg_err is None:
                if not getattr(self, "solve_refine_attempted", False):
                    try:
                        scn["refine_intrinsics_focal_length"] = True
                    except Exception:
                        pass
                    _apply_refine_focal_flag(context, True)
                    try:
                        res_retry = solve_camera_only(context)
                        self.solve_refine_attempted = True
                        self.report({'INFO'}, f"Solve-Retry (avg=None) mit refine_intrinsics_focal_length=True → {res_retry}")
                        return {'RUNNING_MODAL'}
                    except Exception as exc:
                        self.report({'WARNING'}, f"Solve-Retry (avg=None) fehlgeschlagen: {exc}")

                try:
                    red = run_reduce_error_tracks(context, max_to_delete=1)
                    self.report({'INFO'}, f"ReduceErrorTracks(FORCE): delete=1 → done={red.get('deleted')} {red.get('names')}")
                except Exception as _exc:
                    self.report({'WARNING'}, f"ReduceErrorTracks(FORCE) Fehler: {_exc}")

                # reset → neuer Zyklus
                self.detection_threshold = None
                self.pre_ptrs = None
                self.target_frame = None
                self.repeat_map = {}
                self.solve_refine_attempted = False
                self.phase = PH_FIND_LOW
                return {'RUNNING_MODAL'}

            # 3) Ziel erreicht?
            if avg_err <= target_err:
                self.report({'INFO'}, f"Solve OK: avg={avg_err:.4f} ≤ target={target_err:.4f}")
                return self._finish(context, info="Sequenz abgeschlossen (Solve-Ziel erreicht).", cancelled=False)

            # 4) Einmaliger Retry mit Refine, falls noch offen
            if not getattr(self, "solve_refine_attempted", False):
                try:
                    scn["refine_intrinsics_focal_length"] = True
                except Exception:
                    pass
                _apply_refine_focal_flag(context, True)
                try:
                    res_retry = solve_camera_only(context)
                    self.solve_refine_attempted = True
                    self.report({'INFO'}, f"Solve-Retry mit refine_intrinsics_focal_length=True → {res_retry}")
                    return {'RUNNING_MODAL'}
                except Exception as exc:
                    self.report({'WARNING'}, f"Solve-Retry konnte nicht gestartet werden: {exc}")

            # 5) Reduktion: x = ceil(avg/target), clamp 1..20
            import math
            t = target_err if (target_err == target_err and target_err > 1e-8) else 0.6
            x = max(1, min(20, int(math.ceil(avg_err / t))))
            red = run_reduce_error_tracks(context, max_to_delete=x)
            self.report(
                {'INFO'},
                f"ReduceErrorTracks: avg={avg_err:.4f} target={t:.4f} → delete={x} → done={red.get('deleted')} {red.get('names')}"
            )

            # 6) Reset & zurück in den Hauptzyklus
            self.detection_threshold = None
            self.pre_ptrs = None
            self.target_frame = None
            self.repeat_map = {}
            self.solve_refine_attempted = False
            self.phase = PH_FIND_LOW
            return {'RUNNING_MODAL'}

        # PHASE 5: Bidirectional-Tracking (Starten, warten, A_k schreiben)
        if self.phase == PH_BIDI:
            scn = context.scene
            bidi_active = bool(scn.get("bidi_active", False))
            bidi_result = scn.get("bidi_result", "")

            # Operator noch nicht gestartet → starten
            if not self.bidi_started:
                if CLIP_OT_bidirectional_track is None:
                    return self._finish(context, info="Bidirectional-Track nicht verfügbar.", cancelled=True)
                try:
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.bidi_started = True
                    self.report({'INFO'}, "Bidirectional-Track gestartet")
                except Exception as exc:
                    return self._finish(context, info=f"Bidirectional-Track konnte nicht gestartet werden ({exc})",
                                        cancelled=True)
                return {'RUNNING_MODAL'}

            # Operator läuft → abwarten
            if bidi_active:
                return {'RUNNING_MODAL'}

            # Operator hat beendet. Prüfe Ergebnis.
            if str(bidi_result) != "OK":
                return self._finish(context, info=f"Bidirectional-Track fehlgeschlagen ({bidi_result})", cancelled=True)

            # **NEU**: A_k = Σ(frames_pro_Marker × error_value(marker)) schreiben
            try:
                before = self._bidi_before_counts or {}
                after = _snapshot_marker_counts(context)
                per_marker_frames = _delta_marker_counts(before, after)

                try:
                    # Pfad ggf. anpassen, falls deine error_value woanders liegt
                    from ..metrics import error_value  # type: ignore
                except Exception:
                    try:
                        from ..Helper.metrics import error_value  # type: ignore
                    except Exception:
                        def error_value(_track):  # type: ignore
                            return 0.0

                frame = int(self.target_frame) if self.target_frame is not None else context.scene.frame_current
                record_bidirectional_result(
                    context,
                    frame,
                    per_marker_frames=per_marker_frames,
                    error_value_func=error_value,
                )
            except Exception as exc:
                self.report({'WARNING'}, f"A_k-Berechnung/Schreiben fehlgeschlagen: {exc}")

            # Cleanup nach BIDI (beibehalten)
            try:
                clean_short_tracks(context)
                self.report({'INFO'}, "Cleanup nach Bidirectional-Track ausgeführt")
            except Exception as exc:
                self.report({'WARNING'}, f"Cleanup nach Bidirectional-Track fehlgeschlagen: {exc}")

            # Für neue Runde zurücksetzen
            self.detection_threshold = None
            self.pre_ptrs = None
            self.target_frame = None
            self.repeat_map = {}
            self._bidi_before_counts = None
            self.bidi_started = False

            # Startet mit neuer Find-Low-Phase
            self.phase = PH_FIND_LOW
            self.report({'INFO'}, "Bidirectional-Track abgeschlossen – neuer Zyklus beginnt")
            return {'RUNNING_MODAL'}

        # Fallback (unbekannte Phase)
        return self._finish(context, info=f"Unbekannte Phase: {self.phase}", cancelled=True)


# --- Registrierung ----------------------------------------------------------

def register():
    """Registriert den Tracking-Coordinator und optional den Bidirectional-Track Operator."""
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.register_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    """Deregistriert den Tracking-Coordinator und optional den Bidirectional-Track Operator."""
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass


# Optional: lokale Tests beim Direktlauf
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()