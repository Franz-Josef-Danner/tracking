"""
tracking_coordinator.py – Streng sequentieller, MODALER Orchestrator
- Phasen: FIND_LOW → JUMP → DETECT → DISTANZE (hart getrennt, seriell)
- Integration von Anzahl/A₁..A₉ + Abbruch bei 10 + A_k-Schreiben in BIDI
- Jede Phase startet erst, wenn die vorherige abgeschlossen wurde.
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
from ..Helper.reduce_error_tracks import run_reduce_error_tracks, get_avg_reprojection_error  # type: ignore
from ..Helper.reset_state import reset_for_new_cycle  # ← NEU: zentraler Reset

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
from ..Helper.tracker_settings import apply_tracker_settings

# --- Anzahl/A-Werte/State-Handling ------------------------------------------
from ..Helper.tracking_state import (
    orchestrate_on_jump,
    record_bidirectional_result,
    _get_state,          # intern genutzt, um count zu prüfen
    _ensure_frame_entry, # intern genutzt, um Frame-Eintrag zu holen
)
# Fehlerwert-Funktion (Pfad ggf. anpassen)
try:
    from ..Helper.count import error_value  # type: ignore
except Exception:
    try:
        from .count import error_value  # type: ignore
    except Exception:
        def error_value(_track): return 0.0  # Fallback

# ---- Solve-Logger: robust auflösen, ohne auf Paketstruktur zu vertrauen ----
def _solve_log(context, value):
    """Laufzeit-sicherer Aufruf von __init__.kaiserlich_solve_log_add()."""
    try:
        import sys, importlib
        # 1) Root-Paket aus __package__/__name__ ableiten
        root_name = (__package__ or __name__).split(".", 1)[0]
        if not root_name:
            # Fallback: Vermutung "tracking"
            root_name = "tracking"
        mod = sys.modules.get(root_name)
        if mod and hasattr(mod, "kaiserlich_solve_log_add"):
            return getattr(mod, "kaiserlich_solve_log_add")(context, value)
        # 2) Hart nachladen, falls noch nicht importiert
        mod = importlib.import_module(root_name)
        fn = getattr(mod, "kaiserlich_solve_log_add", None)
        if callable(fn):
            return fn(context, value)
    except Exception:
        pass
    # Silent: kein Crash, wenn das Log-Addon noch nicht geladen ist
    return
# Optional: den Bidirectional‑Track Operator importieren. Wenn der Import
# fehlschlägt, bleibt die Variable auf None und es erfolgt kein Aufruf.
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    try:
        from .bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
    except Exception:
        CLIP_OT_bidirectional_track = None  # type: ignore

# -----------------------------------------------------------------------------
# Optionally import the multi-pass helper. This helper performs additional
# feature detection passes with varied pattern sizes. It will be invoked when
# the marker count evaluation reports that the number of markers lies within
# the acceptable range ("ENOUGH").
try:
    # Prefer package-style import when the Helper package is available
    from ..Helper.multi import run_multi_pass  # type: ignore
except Exception:
    try:
        # Fallback to local import when running as a standalone module
        from .multi import run_multi_pass  # type: ignore
    except Exception:
        # If import fails entirely, leave run_multi_pass as None
        run_multi_pass = None  # type: ignore
from ..Helper.marker_helper_main import marker_helper_main
# Import the detect threshold key so we can reference the last used value
try:
    # Local import when running inside the package structure
    from ..Helper.detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
except Exception:
    try:
        # Fallback when module layout differs
        from .detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
    except Exception:
        # Default value if import fails
        DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator",)

# --- Orchestrator-Phasen ----------------------------------------------------
PH_FIND_LOW   = "FIND_LOW"
PH_JUMP       = "JUMP"
PH_DETECT     = "DETECT"
PH_DISTANZE   = "DISTANZE"
PH_SPIKE_CYCLE = "SPIKE_CYCLE"
PH_SOLVE_EVAL = "SOLVE_EVAL"
# Erweiterte Phase: Bidirectional-Tracking. Wenn der Multi‑Pass und das
# Distanz‑Cleanup erfolgreich durchgeführt wurden, wird diese Phase
# angestoßen. Sie startet den Bidirectional‑Track Operator und wartet
# auf dessen Abschluss. Danach beginnt der Koordinator wieder bei PH_FIND_LOW.
PH_BIDI       = "BIDI"

# ---- intern: State Keys / Locks -------------------------------------------
_LOCK_KEY = "tco_lock"

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

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

def _marker_count_by_selected_track(context: bpy.types.Context) -> dict[str, int]:
    """Anzahl Marker je *ausgewähltem* Track (Name -> Count)."""
    clip = _resolve_clip(context)
    out: dict[str, int] = {}
    if not clip:
        return out
    trk = getattr(clip, "tracking", None)
    if not trk:
        return out
    for t in trk.tracks:
        try:
            if getattr(t, "select", False):
                out[t.name] = len(t.markers)
        except Exception:
            pass
    return out

def _delta_counts(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """Delta = after - before (clamp ≥ 0)."""
    names = set(before) | set(after)
    return {n: max(0, int(after.get(n, 0)) - int(before.get(n, 0))) for n in names}

# --- Blender 4.4: Refine-Flag direkt in Tracking-Settings spiegeln ----------
def _apply_refine_focal_flag(context: bpy.types.Context, flag: bool) -> None:
    """Setzt movieclip.tracking.settings.refine_intrinsics_focal_length gemäß flag."""
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
    """
    Snapshot der aktuellen Track-Pointer.
    WICHTIG: Diese Werte NICHT in Scene/IDProperties persistieren (32-bit Limit)!
    Nur ephemer im Python-Kontext verwenden.
    """
    clip = _resolve_clip(context)
    if not clip:
        return []
    try:
        return [int(t.as_pointer()) for t in clip.tracking.tracks]
    except Exception:
        return []

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
        scn["tco_last_marker_helper"] = {"ok": bool(ok), "count": int(count), "info": dict(info) if hasattr(info, "items") else info}
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}
    scn[_LOCK_KEY] = False


# --- Operator: wird vom UI-Button aufgerufen -------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator (Modal, strikt sequenziell)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Modal)"
    # Hinweis: Blender kennt nur GRAB_CURSOR / GRAB_CURSOR_X / GRAB_CURSOR_Y.
    # GRAB_CURSOR_XY existiert nicht → Validation-Error beim Register.
    # Modalität kommt über modal(); Cursor-Grabbing ist nicht nötig.
    bl_options = {"REGISTER", "UNDO"}

    # — Laufzeit-State (nur Operator, nicht Szene) —
    _timer: object | None = None
    phase: str = PH_FIND_LOW
    target_frame: int | None = None
    repeat_map: dict[int, int] = {}
    pre_ptrs: set[int] | None = None
    # Aktueller Detection-Threshold; wird nach jedem Detect-Aufruf aktualisiert.
    detection_threshold: float | None = None
    spike_threshold: float | None = None  # aktueller Spike-Filter-Schwellenwert (temporär)
    # Flag, ob der Bidirectional-Track bereits gestartet wurde. Diese
    # Instanzvariable dient dazu, den Start der Bidirectional‑Track-Phase
    # nur einmal auszulösen und anschließend auf den Abschluss zu warten.
    bidi_started: bool = False
    bidi_before_counts: dict[str, int] | None = None  # Snapshot vor BIDI
    # Temporärer Schwellenwert für den Spike-Cycle (startet bei 100, *0.9)
    # Solve-Retry-State: Wurde bereits mit refine_intrinsics_focal_length=True neu gelöst?
    solve_refine_attempted: bool = False

    def execute(self, context: bpy.types.Context):
        # Bootstrap/Reset
        try:
            _bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator: Bootstrap OK")

        # Harter Neustart aller Runtime-Werte/Listen
        reset_for_new_cycle(context)

        # Modal starten
        self.phase = PH_FIND_LOW
        self.target_frame = None
        self.repeat_map = {}
        self.pre_ptrs = None
        # Threshold-Zurücksetzen: beim ersten Detect-Aufruf wird der Standardwert verwendet
        self.detection_threshold = None
        # Bidirectional‑Track ist noch nicht gestartet
        self.spike_threshold = None  # Spike-Schwellenwert zurücksetzen
        # Solve-Retry-State zurücksetzen
        self.solve_refine_attempted = False
        self.bidi_before_counts = None
        
        wm = context.window_manager
        # --- Robust: valides Window sichern ---
        win = getattr(context, "window", None)
        if not win:
            try:
                # aus dem Clip-Override ziehen
                win = _ensure_clip_context(context).get("window", None)
            except Exception:
                win = None
        if not win:
            # Fallback: globaler Context
            win = getattr(bpy.context, "window", None)
        try:
            # Wenn win None ist, Timer OHNE window anlegen (Blender erlaubt das)
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
            count = int(getattr(self, "_dbg_tick_count", 0)) + 1
            if count <= 3:
                self.report({'INFO'}, f"TIMER tick #{count}, phase={self.phase}")
            self._dbg_tick_count = count
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

            # NEU: Anzahl/Motion-Model orchestrieren und ggf. bei 10 abbrechen
            try:
                orchestrate_on_jump(context, int(self.target_frame))
                # count prüfen (orchestrator zeigt bei ==10 bereits Popup)
                _state = _get_state(context)
                _entry, _ = _ensure_frame_entry(_state, int(self.target_frame))
                _count = int(_entry.get("count", 1))
                if _count >= 10:
                    return self._finish(
                        context,
                        info=f"Abbruch: Frame {self.target_frame} hat 10 Durchläufe.",
                        cancelled=True
                    )
            except Exception as _exc:
                self.report({'WARNING'}, f"Orchestrate on jump warn: {str(_exc)}")

            # **WICHTIG**: Pre-Snapshot direkt vor DETECT
            self.pre_ptrs = set(_snapshot_track_ptrs(context))
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}

        # PHASE 3: DETECT
        if self.phase == PH_DETECT:
            # Beim ersten Detect-Aufruf wird kein Threshold übergeben (None → Standardwert)
            _kwargs: dict[str, object] = {"start_frame": self.target_frame}
            # Wenn bereits ein Threshold aus vorherigen Iterationen vorliegt, diesen mitgeben
            if self.detection_threshold is not None:
                _kwargs["threshold"] = float(self.detection_threshold)
            rd = run_detect_once(context, **_kwargs)
            if rd.get("status") != "READY":
                return self._finish(context, info=f"DETECT FAILED → {rd}", cancelled=True)
            new_cnt = int(rd.get("new_tracks", 0))
            # Merke den verwendeten Threshold für spätere Anpassungen
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
                            # ältere Blender-Builds ohne exact-Param
                            m = t.markers.find_frame(int(self.target_frame))
                        if m:
                            new_ptrs_after_cleanup.add(ptr)

            # Markeranzahl auswerten, sofern die Zählfunktion vorhanden ist.
            eval_res = None
            scn = context.scene
            if evaluate_marker_count is not None:
                try:
                    # Aufruf ohne explizite Grenzwerte – count.py kennt diese selbst.
                    eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_ptrs_after_cleanup)  # type: ignore
                except Exception as exc:
                    # Wenn der Aufruf fehlschlägt, Fehlermeldung zurückgeben.
                    eval_res = {"status": "ERROR", "reason": str(exc), "count": len(new_ptrs_after_cleanup)}
                # Ergebnis im Szenen-Status speichern
                try:
                    scn["tco_last_marker_count"] = eval_res
                except Exception:
                    pass

                # Prüfe, ob Markeranzahl außerhalb des gültigen Bandes liegt
                status = str(eval_res.get("status", "")) if isinstance(eval_res, dict) else ""
                if status in {"TOO_FEW", "TOO_MANY"}:
                    # *** Distanzé-Semantik: nur den MARKER am aktuellen Frame löschen ***
                    deleted_markers = 0
                    if clip and new_ptrs_after_cleanup:
                        trk = getattr(clip, "tracking", None)
                        if trk and hasattr(trk, "tracks"):
                            curf = int(self.target_frame)
                            # Variante 1 (bevorzugt): via Operator im CLIP-Override (robust wie UI)
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
                                # Variante 2 (Fallback): direkte API, ggf. mehrfach löschen bis leer
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
                            # Flush/Refresh, damit der Effekt sofort greift
                            try:
                                bpy.context.view_layer.update()
                                scn.frame_set(curf)
                            except Exception:
                                pass

                    # Threshold neu berechnen:
                    # threshold = max(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                    try:
                        anzahl_neu = float(eval_res.get("count", 0))
                        marker_min = float(eval_res.get("min", 0))
                        marker_max = float(eval_res.get("max", 0))
                        # bevorzugt aus Szene (falls gesetzt), sonst Mittelwert
                        marker_adapt = float(scn.get("marker_adapt", 0.0)) or ((marker_min + marker_max) / 2.0)
                        if marker_adapt <= 0.0:
                            marker_adapt = 1.0
                        base_thr = float(self.detection_threshold if self.detection_threshold is not None
                                         else scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                        self.detection_threshold = max(base_thr * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)

                        # --- NEU: dynamische Werte in der Szene persistieren ---
                        try:
                            # defensiv clampen
                            margin_eff = max(0, int(margin))
                            min_dist_eff = max(1, int(min_distance))
                            scn["margin_base"] = margin_eff
                            scn["min_distance_base"] = min_dist_eff
                            # optionales Log für Transparenz
                            print(f"[Coordinator] scene overrides → margin_base={margin_eff}, "
                                  f"min_distance_base={min_dist_eff}")
                        except Exception as _exc:
                            print(f"[Coordinator] scene override failed: {_exc}")
                    except Exception:
                        pass

                    self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}, deleted_markers={deleted_markers}, thr→{self.detection_threshold}")
                    # Zurück zu DETECT mit neuem Threshold
                    self.phase = PH_DETECT
                    return {'RUNNING_MODAL'}


                # Markeranzahl im gültigen Bereich – optional Multi‑Pass und dann Bidirectional‑Track ausführen.
                did_multi = False
                if isinstance(eval_res, dict) and str(eval_res.get("status", "")) == "ENOUGH":
                    # Führe nur Multi‑Pass aus, wenn der Helper importiert werden konnte.
                    if run_multi_pass is not None:
                        try:
                            # Snapshot der aktuellen Tracker‑Pointer als Basis für den Multi‑Pass.
                            current_ptrs = set(_snapshot_track_ptrs(context))
                            # Ermittelten Threshold für den Multi‑Pass verwenden. Fallback auf einen Standardwert.
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
                            self.report({'INFO'}, f"MULTI-PASS ausgeführt: created_low={mp_res.get('created_low')}, created_high={mp_res.get('created_high')}, selected={mp_res.get('selected')}")
                            # Nach dem Multi‑Pass eine Distanzprüfung durchführen.
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
                                    self.report({'INFO'}, f"MULTI-PASS DISTANZE: removed={dist_res.get('removed')}, kept={dist_res.get('kept')}")
                            except Exception as exc:
                                self.report({'WARNING'}, f"Multi-Pass Distanzé-Aufruf fehlgeschlagen ({exc})")
                            did_multi = True
                        except Exception as exc:
                            # Bei Fehlern im Multi‑Pass nicht abbrechen, sondern warnen.
                            self.report({'WARNING'}, f"Multi-Pass-Aufruf fehlgeschlagen ({exc})")
                    else:
                        # Multi‑Pass ist nicht verfügbar (Import fehlgeschlagen)
                        self.report({'WARNING'}, "Multi-Pass nicht verfügbar – kein Aufruf durchgeführt")
                    # Wenn ein Multi‑Pass ausgeführt wurde, starte nun die Bidirectional‑Track-Phase.
                    if did_multi:
                        # Wechsle in die Bidirectional‑Phase. Die Bidirectional‑Track-Operation
                        # selbst wird im Modal-Handler ausgelöst. Nach Abschluss dieser Phase
                        # wird der Zyklus erneut bei PH_FIND_LOW beginnen.
                        self.phase = PH_BIDI
                        self.bidi_started = False
                        self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res} – Starte Bidirectional-Track")
                        return {'RUNNING_MODAL'}
                # In allen anderen Fällen (kein ENOUGH oder kein Multi‑Pass) wird die Sequenz beendet.
                self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}")
                return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)

            # Wenn keine Auswertungsfunktion vorhanden ist, einfach abschließen
            self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}")
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
            _solve_log(context, avg_err)  # loggt nur bei gültigem numerischem Wert
            # 2) kein Wert → Retry einmalig, sonst mind. 1 Track löschen
            if avg_err is None:
                if not getattr(self, "solve_refine_attempted", False):
                    try: scn["refine_intrinsics_focal_length"] = True
                    except Exception: pass
                    _apply_refine_focal_flag(context, True)
                    try:
                        res_retry = solve_camera_only(context)
                        self.solve_refine_attempted = True
                        self.report({'INFO'}, f"Solve-Retry (avg=None) mit refine_intrinsics_focal_length=True → {res_retry}")
                        return {'RUNNING_MODAL'}
                    except Exception as exc:
                        self.report({'WARNING'}, f"Solve-Retry (avg=None) fehlgeschlagen: {exc}")
                # erzwungen 1 löschen
                try:
                    red = run_reduce_error_tracks(context, max_to_delete=1)
                    self.report({'INFO'}, f"ReduceErrorTracks(FORCE): delete=1 → done={red.get('deleted')} {red.get('names')}")
                except Exception as _exc:
                    self.report({'WARNING'}, f"ReduceErrorTracks(FORCE) Fehler: {_exc}")
                # reset → neuer Zyklus
                reset_for_new_cycle(context)
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
                try: scn["refine_intrinsics_focal_length"] = True
                except Exception: pass
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
            self.report({'INFO'}, f"ReduceErrorTracks: avg={avg_err:.4f} target={t:.4f} → delete={x} → done={red.get('deleted')} {red.get('names')}")
            # 6) Reset & zurück in den Hauptzyklus
            reset_for_new_cycle(context)
            self.detection_threshold = None
            self.pre_ptrs = None
            self.target_frame = None
            self.repeat_map = {}
            self.solve_refine_attempted = False
            self.phase = PH_FIND_LOW
            return {'RUNNING_MODAL'}

        # PHASE: SPIKE_CYCLE – spike_filter → clean_short_segments → clean_short_tracks → split_cleanup → find_max_marker_frame
        if self.phase == PH_SPIKE_CYCLE:
            scn = context.scene
            thr = float(self.spike_threshold or 100.0)
            # 1) Spike-Filter
            try:
                run_marker_spike_filter_cycle(context, track_threshold=thr)
            except Exception as exc:
                return self._finish(context, info=f"SPIKE_CYCLE spike_filter failed: {exc}", cancelled=True)
            # 2) Segment-/Track-Cleanup
            try:
                clean_short_segments(context, min_len=int(scn.get("tco_min_seg_len", 25)))
            except Exception:
                pass
            try:
                clean_short_tracks(context)
            except Exception:
                pass
            # 3) Split-Cleanup (UI-override, falls verfügbar)
            try:
                override = _ensure_clip_context(context)
                space = override.get("space_data") if override else None
                clip = getattr(space, "clip", None) if space else None
                tracks = clip.tracking.tracks if clip else None
                if override and tracks:
                    with bpy.context.temp_override(**override):
                        recursive_split_cleanup(context, **override, tracks=tracks)
            except Exception:
                pass
            # 4) Max-Marker-Frame suchen
            rmax = run_find_max_marker_frame(context)
            if rmax.get("status") == "FOUND":
                # Erfolg → regulären Zyklus neu starten
                reset_for_new_cycle(context)
                self.spike_threshold = None
                scn["tco_spike_cycle_finished"] = False
                self.phase = PH_FIND_LOW
                return {'RUNNING_MODAL'}
            # Kein Treffer
            next_thr = thr * 0.9
            if next_thr < 10.0:
                # Terminalbedingung: Spike-Cycle beendet → Kamera-Solve starten
                try:
                    scn["tco_spike_cycle_finished"] = True
                except Exception:
                    pass
                try:
                    # Erstlauf: refine_intrinsics_focal_length explizit deaktivieren
                    try:
                        scn["refine_intrinsics_focal_length"] = False
                    except Exception:
                        pass
                    # Flag unmittelbar in die Tracking-Settings spiegeln (erster Solve ohne Refine)
                    _apply_refine_focal_flag(context, False)
                    self.solve_refine_attempted = False
                    res = solve_camera_only(context)
                    self.report({'INFO'}, f"SolveCamera gestartet → {res}")
                    # → direkt in die Solve-Evaluation wechseln
                    self.phase = PH_SOLVE_EVAL
                    return {'RUNNING_MODAL'}
                except Exception as exc:
                    return self._finish(context, info=f"SolveCamera start fehlgeschlagen: {exc}", cancelled=True)
            # Weiter iterieren
            self.spike_threshold = next_thr
            return {'RUNNING_MODAL'}
        # PHASE 5: Bidirectional-Tracking. Wird aktiviert, nachdem ein Multi-Pass
        # und Distanzé erfolgreich ausgeführt wurden und die Markeranzahl innerhalb des
        # gültigen Bereichs lag. Startet den Bidirectional-Track-Operator und wartet
        # auf dessen Abschluss. Danach wird die Sequenz wieder bei PH_FIND_LOW fortgesetzt.
        if self.phase == PH_BIDI:
            scn = context.scene
            bidi_active = bool(scn.get("bidi_active", False))
            bidi_result = scn.get("bidi_result", "")
            # Operator noch nicht gestartet → starten
            if not self.bidi_started:
                if CLIP_OT_bidirectional_track is None:
                    return self._finish(context, info="Bidirectional-Track nicht verfügbar.", cancelled=True)
                try:
                    # Snapshot vor Start (nur ausgewählte Tracks)
                    self.bidi_before_counts = _marker_count_by_selected_track(context)
                    # Starte den Bidirectional‑Track mittels Operator. Das 'INVOKE_DEFAULT'
                    # sorgt dafür, dass Blender den Operator modal ausführt.
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.bidi_started = True
                    self.report({'INFO'}, "Bidirectional-Track gestartet")
                except Exception as exc:
                    return self._finish(context, info=f"Bidirectional-Track konnte nicht gestartet werden ({exc})", cancelled=True)
                return {'RUNNING_MODAL'}
            # Operator läuft → abwarten
            if not bidi_active:
                # Operator hat beendet. Prüfe Ergebnis.
                if str(bidi_result) != "OK":
                    return self._finish(context, info=f"Bidirectional-Track fehlgeschlagen ({bidi_result})", cancelled=True)
                # NEU: Delta je Marker berechnen und A_k speichern
                try:
                    before = self.bidi_before_counts or {}
                    after = _marker_count_by_selected_track(context)
                    per_marker_frames = _delta_counts(before, after)
                    # Ziel-Frame bestimmen (Fallback auf aktuellen Scene-Frame)
                    f = int(self.target_frame) if self.target_frame is not None else int(context.scene.frame_current)
                    record_bidirectional_result(
                        context,
                        f,
                        per_marker_frames=per_marker_frames,
                        error_value_func=error_value,
                    )
                    self.report({'INFO'}, f"A_k gespeichert @f{f}: sumΔ={sum(per_marker_frames.values())}")
                except Exception as _exc:
                    self.report({'WARNING'}, f"A_k speichern fehlgeschlagen: {_exc}")
                # Erfolgreich: für die neue Runde zurücksetzen
                try:
                    clean_short_tracks(context)
                    self.report({'INFO'}, "Cleanup nach Bidirectional-Track ausgeführt")
                except Exception as exc:
                    self.report({'WARNING'}, f"Cleanup nach Bidirectional-Track fehlgeschlagen: {exc}")
                reset_for_new_cycle(context)
                self.detection_threshold = None
                self.pre_ptrs = None
                self.target_frame = None
                self.repeat_map = {}
                self.bidi_started = False
                self.bidi_before_counts = None
                # Startet mit neuer Find-Low-Phase
                self.phase = PH_FIND_LOW
                self.report({'INFO'}, "Bidirectional-Track abgeschlossen – neuer Zyklus beginnt")
                return {'RUNNING_MODAL'}
            # Wenn noch aktiv → weiter warten
            return {'RUNNING_MODAL'}

        # Fallback (unbekannte Phase)
        return self._finish(context, info=f"Unbekannte Phase: {self.phase}", cancelled=True)
        # --- Ende modal() ---

# --- Registrierung ----------------------------------------------------------
def register():
    """Registriert den Tracking‑Coordinator und optional den Bidirectional‑Track Operator."""
    # Den Bidirectional‑Track Operator zuerst registrieren, falls verfügbar. Dieser
    # kann aus Helper/bidirectional_track.py importiert werden. Wenn der Import
    # fehlschlägt, bleibt die Variable None.
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.register_class(CLIP_OT_bidirectional_track)
        except Exception:
            # Ignoriere Fehler, Operator könnte bereits registriert sein
            pass
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    """Deregistriert den Tracking‑Coordinator und optional den Bidirectional‑Track Operator."""
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass
    # Optional auch den Bidirectional‑Track Operator deregistrieren
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
