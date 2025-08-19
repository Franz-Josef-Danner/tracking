"""Blender-Add-on – funktionaler Optimierungs‑Flow (keine Operatoren)

NEU in dieser Variante
----------------------
• Vor der Motion/Channel‑Optimierung läuft nun ein **Pattern‑Size‑Sweep**,
  der erst beendet wird, wenn die Qualitätsmetrik (EGA) **signifikant**
  unter den bisher besten Wert fällt (relativer Abstieg > drop_threshold),
  und **mindestens min_sweep_steps** Samples gesammelt wurden.
• Beste (pt, sus) aus dem Sweep werden als ptv festgehalten und anschließend
  in die Motion‑/Channel‑Schleifen übernommen.

Parameter
---------
• sweep_step_factor: Multiplikator für Pattern‑Size‑Erhöhung pro Schritt (Default 1.1)
• drop_threshold:     relativer Abstieg gegenüber best_ega, z. B. 0.12 = 12%
• min_sweep_steps:    Mindestanzahl von Messpunkten, bevor abgebrochen werden darf
• soft_patience:      Anzahl tolerierter **nicht**‑signifikanter Nicht‑Verbesserungen,
                       bevor wir vorsorglich beenden (Failsafe)

Hinweis
-------
Die restliche Struktur (Detect/Track‑Helper, Motion‑ & Channel‑Loops) bleibt
unverändert. Der frühere DG‑Zähler entfällt im Sweep und wird durch die klare
Abbruchbedingung „signifikanter Abstieg“ ersetzt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

import bpy

# -----------------------------------------------------------------------------
# Dynamische Helper‑Imports (wie in der neuen Variante)
# -----------------------------------------------------------------------------
try:
    from .detect import run_detect_once  # type: ignore
except Exception:  # pragma: no cover
    run_detect_once = None  # type: ignore

try:
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

try:
    from .error_value import error_value  # type: ignore
except Exception:  # pragma: no cover
    error_value = None  # type: ignore

# -----------------------------------------------------------------------------
# Konfiguration & Mapping
# -----------------------------------------------------------------------------
MOTION_MODELS: List[str] = [
    "Perspective",
    "Affine",
    "LocRotScale",
    "LocScale",
    "LocRot",
]

CHANNEL_PRESETS = {
    0: (True, False, False),
    1: (True, True, False),
    2: (False, True, False),
    3: (False, True, True),
}

# -----------------------------------------------------------------------------
# Flag‑Setter
# -----------------------------------------------------------------------------

def _set_flag1(clip: bpy.types.MovieClip, pattern: int, search: int) -> None:
    s = clip.tracking.settings
    s.default_pattern_size = int(pattern)
    s.default_search_size = int(search)
    s.default_margin = s.default_search_size


def _set_flag2_motion_model(clip: bpy.types.MovieClip, model_index: int) -> None:
    if 0 <= model_index < len(MOTION_MODELS):
        clip.tracking.settings.default_motion_model = MOTION_MODELS[model_index]


def _set_flag3_channels(clip: bpy.types.MovieClip, vv: int) -> None:
    r, g, b = CHANNEL_PRESETS.get(vv, (True, True, True))
    s = clip.tracking.settings
    s.use_default_red_channel = bool(r)
    s.use_default_green_channel = bool(g)
    s.use_default_blue_channel = bool(b)

# -----------------------------------------------------------------------------
# EGA‑Metrik: Σ (frames_per_track / error_per_track)
# -----------------------------------------------------------------------------

def _calc_track_quality_sum(context: bpy.types.Context, clip: bpy.types.MovieClip) -> float:
    total = 0.0
    for ob in clip.tracking.objects:
        for tr in ob.tracks:
            err = None
            if error_value is not None:
                try:
                    err = float(error_value(context, tr))  # type: ignore[misc]
                except TypeError:
                    try:
                        sel_backup = tr.select
                        tr.select = True
                        err = float(error_value(context.scene))  # type: ignore[misc]
                    finally:
                        try:
                            tr.select = sel_backup
                        except Exception:
                            pass
                except Exception:
                    err = None
            if err is None:
                err = float(getattr(tr, "average_error", 0.0) or 0.0)
            err = max(err, 1e-12)
            frames = max(len(tr.markers), 1)
            total += (frames / err)
    return float(total)

# -----------------------------------------------------------------------------
# UI‑Kontexthilfen
# -----------------------------------------------------------------------------

def _find_clip_editor_context(context):
    wm = context.window_manager
    if not wm:
        return None
    for win in wm.windows:
        screen = win.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if region and space:
                return win, area, region, space
    return None


def _call_in_clip_context(context, fn, *, ensure_tracking_mode=True, **kwargs):
    found = _find_clip_editor_context(context)
    if not found:
        return fn(**kwargs)
    win, area, region, space = found
    override = {
        "window": win,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": context.scene,
    }
    with context.temp_override(**override):
        if ensure_tracking_mode and hasattr(space, "mode") and space.mode != 'TRACKING':
            try:
                space.mode = 'TRACKING'
            except Exception:
                pass
        return fn(**kwargs)


def _delete_selected_tracks(context: bpy.types.Context) -> None:
    def _op(**kw):
        return bpy.ops.clip.delete_track(**kw)
    try:
        _call_in_clip_context(context, _op, ensure_tracking_mode=True, confirm=True)
        print("[Optimize] Selektierte (neue) Marker/Tracks gelöscht.")
    except Exception as ex:
        print(f"[Optimize] WARN: delete_track fehlgeschlagen: {ex}")

# -----------------------------------------------------------------------------
# Async‑Tracking bis Szenenende (Token‑basiert)
# -----------------------------------------------------------------------------
@dataclass
class _AsyncTracker:
    context: bpy.types.Context
    origin_frame: int
    token: str = field(default_factory=lambda: f"bw_optimize_token_{id(object())}")

    def start(self) -> None:
        assert track_to_scene_end_fn is not None, "tracking_helper fehlt"
        wm = self.context.window_manager
        if wm.get("bw_tracking_done_token", None) == self.token:
            del wm["bw_tracking_done_token"]
        def _kickoff(**kw):
            return track_to_scene_end_fn(self.context, **kw)
        _call_in_clip_context(
            self.context,
            _kickoff,
            ensure_tracking_mode=True,
            coord_token=self.token,
            start_frame=int(self.origin_frame),
            debug=True,
            first_delay=0.25,
        )

    def done(self) -> bool:
        return self.context.window_manager.get("bw_tracking_done_token", None) == self.token

    def clear(self) -> None:
        wm = self.context.window_manager
        if wm.get("bw_tracking_done_token", None) == self.token:
            del wm["bw_tracking_done_token"]

# -----------------------------------------------------------------------------
# Hauptzustand
# -----------------------------------------------------------------------------
@dataclass
class _State:
    context: bpy.types.Context
    clip: bpy.types.MovieClip
    origin_frame: int

    # Pattern‑Sweep‑Parameter
    sweep_step_factor: float = 1.10
    drop_threshold: float = 0.12     # 12% relativer Abstieg
    min_sweep_steps: int = 3
    soft_patience: int = 3           # tolerierte leichte Nicht‑Verbesserungen

    # Dynamik
    pt: float = 21.0
    sus: float = 42.0

    # Sweep‑Tracking
    sweep_history: List[Tuple[float, float]] = field(default_factory=list)  # (pt, ega)
    best_ega: float = -1.0
    best_pt: float = 21.0
    since_best: int = 0

    # Ergebnis‑Vorhalte
    ptv: float = 21.0
    ev: float = -1.0

    # Motion/Channel
    mo_index: int = 0
    mov: int = 0
    vv: int = 0
    vf: int = 0

    phase: str = "INIT"
    tracker: Optional[_AsyncTracker] = None

# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------
_RUNNING: Optional[_State] = None


def start_optimization(context: bpy.types.Context) -> None:
    cancel_optimization()
    space = getattr(context, "space_data", None)
    if not space or getattr(space, "type", "") != "CLIP_EDITOR":
        print("[Optimize] WARN: Kein CLIP_EDITOR aktiv – fahre trotzdem fort.")
    clip = getattr(space, "clip", None) or getattr(context.space_data, "clip", None)
    if not clip:
        raise RuntimeError("Kein aktiver Movie Clip.")

    st = _State(context=context, clip=clip, origin_frame=int(context.scene.frame_current))
    st.phase = "SWEEP_INIT"
    globals()["_RUNNING"] = st

    bpy.app.timers.register(_timer_step, first_interval=0.2)
    print(f"[Optimize] Start @frame={st.origin_frame}")


def cancel_optimization() -> None:
    global _RUNNING
    _RUNNING = None

# -----------------------------------------------------------------------------
# Timer‑Step
# -----------------------------------------------------------------------------

def _timer_step() -> float | None:
    st = globals().get("_RUNNING")
    if not st:
        return None
    try:
        # -------------------- PATTERN‑SWEEP --------------------
        if st.phase == "SWEEP_INIT":
            # Erste Flags setzen, Marker sicherstellen, ersten Track starten
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            st.phase = "SWEEP_WAIT_BASE"
            return 0.1

        if st.phase == "SWEEP_WAIT_BASE":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            _delete_selected_tracks(st.context)  # Aufräumen NACH dem Messen
            st.sweep_history.append((st.pt, ega))
            st.best_ega = ega
            st.best_pt = st.pt
            st.ptv = st.pt
            st.ev = ega
            st.since_best = 0
            # nächster Schritt
            st.pt = st.pt * st.sweep_step_factor
            st.sus = st.pt * 2
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            st.phase = "SWEEP_WAIT_RUN"
            return 0.1

        if st.phase == "SWEEP_WAIT_RUN":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            _delete_selected_tracks(st.context)  # Aufräumen NACH dem Messen
            st.sweep_history.append((st.pt, ega))

            # Update best
            improved = ega > st.best_ega
            if improved:
                st.best_ega = ega
                st.best_pt = st.pt
                st.ptv = st.pt
                st.ev = ega
                st.since_best = 0
            else:
                st.since_best += 1

            # Abbruchbedingung: signifikanter Abstieg (und genug Samples)
            significant_drop = (st.best_ega > 0.0 and (ega < st.best_ega * (1.0 - st.drop_threshold)))
            enough_steps = len(st.sweep_history) >= st.min_sweep_steps
            soft_stop = st.since_best >= st.soft_patience

            if (significant_drop and enough_steps) or soft_stop:
                # auf best_pt zurücksetzen und Motion/Channel beginnen
                st.pt = st.best_pt
                st.sus = st.pt * 2
                _set_flag1(st.clip, int(st.pt), int(st.sus))
                print(
                    f"[Sweep] Ende: best_ega={st.best_ega:.3f} @ pt={st.best_pt:.1f}; "
                    f"last_ega={ega:.3f}; steps={len(st.sweep_history)}"
                )
                st.mo_index = 0
                st.mov = 0
                st.vv = 0
                st.vf = 0
                st.phase = "MOTION_LOOP_RUN"
                return 0.0

            # ansonsten: weiter erhöhen
            st.pt = st.pt * st.sweep_step_factor
            st.sus = st.pt * 2
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            return 0.1

        # -------------------- MOTION‑LOOP --------------------
        if st.phase == "MOTION_LOOP_RUN":
            if st.mo_index >= len(MOTION_MODELS):
                st.vv = 0
                st.vf = 0
                st.phase = "CHANNEL_LOOP_RUN"
                return 0.0
            _set_flag2_motion_model(st.clip, st.mo_index)
            _ensure_markers(st)
            _start_track(st)
            st.phase = "MOTION_WAIT"
            return 0.1

        if st.phase == "MOTION_WAIT":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            _delete_selected_tracks(st.context)  # Aufräumen NACH dem Messen
            if ega > st.ev:
                st.ev = ega
                st.mov = st.mo_index
            st.mo_index += 1
            st.phase = "MOTION_LOOP_RUN"
            return 0.0

        # -------------------- CHANNEL‑LOOP --------------------
        if st.phase == "CHANNEL_LOOP_RUN":
            if st.vv >= len(CHANNEL_PRESETS):
                _apply_best_and_finish(st)
                return None
            _set_flag3_channels(st.clip, st.vv)
            _ensure_markers(st)
            _start_track(st)
            st.phase = "CHANNEL_WAIT"
            return 0.1

        if st.phase == "CHANNEL_WAIT":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            _delete_selected_tracks(st.context)  # Aufräumen NACH dem Messen
            if ega > st.ev:
                st.ev = ega
                st.vf = st.vv
            st.vv += 1
            st.phase = "CHANNEL_LOOP_RUN"
            return 0.0

        print(f"[Optimize] Unbekannte Phase: {st.phase}")
        globals()["_RUNNING"] = None
        return None

    except Exception as ex:  # noqa: BLE001
        print(f"[Optimize] Fehler: {ex}")
        globals()["_RUNNING"] = None
        return None

# -----------------------------------------------------------------------------
# Ablauf‑Helfer
# -----------------------------------------------------------------------------

def _ensure_markers(st: _State) -> None:
    if run_detect_once is None:
        return
    try:
        # Führe Detect IMMER im Clip-Editor-Kontext aus, damit space_data.clip garantiert vorhanden ist.
        def _kickoff(**kw):
            # run_detect_once erwartet den Context als erstes Argument
            return run_detect_once(st.context, **kw)
        _call_in_clip_context(
            st.context,
            _kickoff,
            ensure_tracking_mode=True,
            start_frame=st.origin_frame,
            handoff_to_pipeline=False,
        )
    except AttributeError as ex:
        # Häufige Ursache: "'NoneType' object has no attribute 'clip'" wenn kein gültiger space_data gesetzt ist.
        print(f"[Detect] WARN: Kontextproblem bei Detect ({ex}) – erneuter Versuch im Clip-Kontext…")
        try:
            _call_in_clip_context(
                st.context,
                _kickoff,
                ensure_tracking_mode=True,
                start_frame=st.origin_frame,
                handoff_to_pipeline=False,
            )
        except Exception:
            pass
    except Exception:
        pass

def _start_track(st: _State) -> None:
    if st.tracker:
        st.tracker.clear()
    st.tracker = _AsyncTracker(st.context, st.origin_frame)
    st.tracker.start()


def _finish_track(st: _State) -> None:
    if st.tracker:
        st.tracker.clear()
    cur = int(st.context.scene.frame_current)
    if cur != st.origin_frame:
        try:
            st.context.scene.frame_set(st.origin_frame)
        except Exception:
            st.context.scene.frame_current = st.origin_frame



def _apply_best_and_finish(st: _State) -> None:
    _set_flag2_motion_model(st.clip, st.mov)
    _set_flag3_channels(st.clip, st.vf)
    print(
        f"[Optimize] Fertig. ev={st.ev:.3f}, Motion={st.mov}, Channels={st.vf}, pt≈{st.ptv:.1f}"
    )
    globals()["_RUNNING"] = None

# -----------------------------------------------------------------------------
# Komfort‑Alias
# -----------------------------------------------------------------------------

def optimize_now(context: bpy.types.Context) -> None:
    start_optimization(context)
