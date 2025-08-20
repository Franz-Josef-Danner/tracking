# Blender-Add-on – funktionaler Optimierungs‑Flow (keine Operatoren)
#
# Hinweis: Diese Datei ist **rein funktional** (keine Operatoren). Die Steuerung
# erfolgt über `bpy.app.timers` und Helper-Funktionen (Detect/Track), identisch
# zur neuen Version. Gegenüber der letzten Revision sind nur **Syntax‑Fixes** und
# die korrekte **mehrstufige Pattern‑Size‑Suche** nach alter Version enthalten.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

import bpy

from .set_test_value import set_test_value

# =============================================================================
# Dynamische Helper‑Imports (gleichen Signaturen wie in optimize_tracking_modal_neu)
# =============================================================================
try:  # Detect-Einzelpass
    from .detect import run_detect_once  # type: ignore
except Exception:  # pragma: no cover
    run_detect_once = None  # type: ignore

try:  # Async‑Tracking bis Szenenende, setzt ein Done‑Token im WindowManager
    from .tracking_helper import track_to_scene_end_fn  # type: ignore
except Exception:  # pragma: no cover
    track_to_scene_end_fn = None  # type: ignore

try:  # Fehler/Qualitätsmetrik (aus altem System)
    from .error_value import error_value  # type: ignore
except Exception:  # pragma: no cover
    error_value = None  # type: ignore


# =============================================================================
# Konfiguration & Mapping (Syntax‑bereinigt)
# =============================================================================
MOTION_MODELS: List[str] = [
    "Perspective",   # 0
    "Affine",        # 1
    "LocRotScale",   # 2
    "LocScale",      # 3
    "LocRot",        # 4
]

# Channel‑Preset gemäß Vorgabe (hier nur Mapping; Umschaltung am Ende)
CHANNEL_PRESETS = {
    0: (True, False, False),
    1: (True, True, False),
    2: (False, True, False),
    3: (False, True, True),
}

# --- Pattern‑Size‑Suche / Hysterese ---
DETERIORATION_RATIO: float = 0.12   # 12% schlechter als aktueller Bestwert ⇒ signifikant
MIN_SAME_PT_REPEATS: int = 3        # Bestätigungsläufe am selben pt

# --- NEU: Robustheit, wenn ein Track‑Run "nichts bringt" (EGA≈0) ---
NO_RESULT_EGA: float = 1e-9         # EGA ~ 0 ⇒ kein verwertbares Ergebnis
PT_GROWTH_FAST: float = 1.25        # schneller Schritt, wenn gar nichts kam
PT_GROWTH: float = 1.10             # normaler Schritt
PT_MAX: int = 121                   # Sicherheitskappe für Pattern‑Size

_LOCK_KEY = "__detect_lock"

# =============================================================================
# Hilfsfunktionen: Flags / Defaults setzen
# =============================================================================
# Helper/optimize_tracking_modal.py

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


def _bump_pattern(st: "_State", *, fast: bool = False) -> None:
    """Pattern/Search vergrößern, Flags setzen, Detect+Track erneut starten."""
    factor = PT_GROWTH_FAST if fast else PT_GROWTH
    st.pt = min(float(PT_MAX), st.pt * factor)
    st.sus = st.pt * 2.0
    _set_flag1(st.clip, int(st.pt), int(st.sus))
    _ensure_markers(st)
    _start_track(st)


# =============================================================================
# Metriken: EGA = Σ (frames_per_track / error_per_track)
# =============================================================================

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
                    except Exception:
                        pass
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


# =============================================================================
# CLIP_EDITOR‑Kontext & Utilities
# =============================================================================

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
        _call_in_clip_context(context, _op, ensure_tracking_mode=True, confirm=False)
        print("[Optimize] Selektierte (neue) Marker/Tracks gelöscht.")
    except Exception as ex:
        print(f"[Optimize] WARN: delete_track fehlgeschlagen: {ex}")


# =============================================================================
# Async‑Tracking Orchestration (Timer + Done‑Token)
# =============================================================================
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


# =============================================================================
# Hauptzustand der Optimierung
# =============================================================================
@dataclass
class _State:
    context: bpy.types.Context
    clip: bpy.types.MovieClip
    origin_frame: int

    ev: float = -1.0
    dg: int = 0
    pt: float = 21.0
    ptv: float = 21.0
    sus: float = 42.0

    mo_index: int = 0
    mov: int = 0

    vv: int = 0
    vf: int = 0

    phase: str = "INIT"
    tracker: Optional[_AsyncTracker] = None

    # Hysterese nach alter Version
    rep_same_pt: int = 0


# =============================================================================
# Timer‑Pipeline
# =============================================================================
_RUNNING: Optional[_State] = None


def start_optimization(context: bpy.types.Context) -> None:
    # 1) sauberen Zustand sicherstellen
    cancel_optimization()

    # 2) Clip/Editor ermitteln
    space = getattr(context, "space_data", None)
    if not space or getattr(space, "type", "") != "CLIP_EDITOR":
        print("[Optimize] WARN: Kein CLIP_EDITOR aktiv – fahre trotzdem fort.")
    clip = getattr(space, "clip", None) or getattr(context.space_data, "clip", None)
    if not clip:
        raise RuntimeError("Kein aktiver Movie Clip.")

    # 3) Startframe einfrieren (wichtig für Detect-Seed & Async-Tracker)
    origin = int(context.scene.frame_current)

    try:
        context.scene[_LOCK_KEY] = True
    except Exception:
        pass
    # 4) Jetzt – und nur jetzt – die Voreinstellung setzen
    try:
        set_test_value(context.scene)  # schreibt marker_basis/adapt/min/max
        print("[Bootstrap] set_test_value() vor FLAG1_INIT angewendet.")
    except Exception as ex:
        print(f"[Bootstrap] WARN @start_optimization: {ex}")

    # 5) Optimizer-State aufbauen und Timer starten
    st = _State(context=context, clip=clip, origin_frame=origin)
    st.phase = "FLAG1_INIT"
    globals()["_RUNNING"] = st
    bpy.app.timers.register(_timer_step, first_interval=0.2)
    print(f"[Optimize] Start @frame={st.origin_frame}")


def cancel_optimization() -> None:
    global _RUNNING
    if _RUNNING:
        try:
            _RUNNING.context.scene[_LOCK_KEY] = False
        except Exception:
            pass
    _RUNNING = None



def _timer_step() -> float | None:
    st = globals().get("_RUNNING")
    if not st:
        return None
    try:
        if st.phase == "FLAG1_INIT":
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            st.phase = "WAIT_TRACK_BASE"
            return 0.1

        if st.phase == "WAIT_TRACK_BASE":
            if not st.tracker or not st.tracker.done():
                return 0.1
            ega = _calc_track_quality_sum(st.context, st.clip)
            _finish_track(st)

            if ega <= NO_RESULT_EGA:
                print(f"[Optimize] Kein Tracking-Ergebnis bei pt={st.pt:.1f} → erhöhe Pattern (fast) & wiederhole Basis.")
                _bump_pattern(st, fast=True)
                st.phase = "WAIT_TRACK_BASE"
                return 0.1

            if st.ev < 0:
                st.ev = ega
                _bump_pattern(st, fast=False)
                st.phase = "WAIT_TRACK_IMPROVE"
                return 0.1

            return _branch_ev_known(st, ega)

        if st.phase == "WAIT_TRACK_IMPROVE":
            if not st.tracker or not st.tracker.done():
                return 0.1
            ega = _calc_track_quality_sum(st.context, st.clip)
            _finish_track(st)
            return _branch_ev_known(st, ega)

        if st.phase == "MOTION_LOOP_SETUP":
            st.pt = st.ptv
            st.sus = st.pt * 2
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            st.mo_index = 0
            st.mov = 0
            st.phase = "MOTION_LOOP_RUN"
            return 0.0

        if st.phase == "MOTION_LOOP_RUN":
            if st.mo_index >= 5:
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
            ega = _calc_track_quality_sum(st.context, st.clip)
            _finish_track(st)
            if ega > st.ev:
                st.ev = ega
                st.mov = st.mo_index
            st.mo_index += 1
            st.phase = "MOTION_LOOP_RUN"
            return 0.0

        if st.phase == "CHANNEL_LOOP_RUN":
            if st.vv >= 4:
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
            ega = _calc_track_quality_sum(st.context, st.clip)
            _finish_track(st)
            if ega > st.ev:
                st.ev = ega
                st.vf = st.vv
            st.vv += 1
            st.phase = "CHANNEL_LOOP_RUN"
            return 0.0

        # Fallback – sollte eigentlich nie passieren
        print(f"[Optimize] Unbekannte Phase: {st.phase}")
        globals()["_RUNNING"] = None
        return None

    except Exception as ex:
        print(f"[Optimize] Fehler: {ex}")
        try:
            st.context.scene[_LOCK_KEY] = False
        except Exception:
            pass
        globals()["_RUNNING"] = None
        return None
# =============================================================================
# Branch‑Helfer (Pattern‑Suche mit Hysterese nach alter Version + No-Result-Handling)
# =============================================================================

def _branch_ev_known(st: _State, ega: float) -> float:
    # Kein Ergebnis? → nicht als "schlechter" werten, sondern Pattern anheben & weiter testen
    if ega <= NO_RESULT_EGA:
        print(f"[Optimize] EGA≈0 bei pt={st.pt:.1f} → Pattern anheben (fast) & erneut testen.")
        st.rep_same_pt = 0
        _bump_pattern(st, fast=True)
        st.phase = "WAIT_TRACK_IMPROVE"
        return 0.1

    # Verbesserung
    if ega > st.ev:
        st.ev = ega
        st.dg = 4
        st.ptv = st.pt
        st.rep_same_pt = 0
        _bump_pattern(st, fast=False)
        st.phase = "WAIT_TRACK_IMPROVE"
        return 0.1

    # signifikant schlechter?
    worse_ratio = (st.ev - ega) / max(1e-12, st.ev) if st.ev > 0 else 0.0
    if worse_ratio >= DETERIORATION_RATIO:
        st.rep_same_pt += 1
        print(f"[Optimize] Signifikant schlechter ({worse_ratio:.2%}) – Bestätigung {st.rep_same_pt}/{MIN_SAME_PT_REPEATS} @pt={st.pt:.1f}")
        if st.rep_same_pt < MIN_SAME_PT_REPEATS:
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            st.phase = "WAIT_TRACK_IMPROVE"
            return 0.1
        # genug bestätigt → auf ptv zurück und Motion/Channel starten
        st.pt = st.ptv
        st.sus = st.pt * 2
        st.rep_same_pt = 0
        st.phase = "MOTION_LOOP_SETUP"
        return 0.0

    # weder besser noch signifikant schlechter → degression
    st.rep_same_pt = 0
    st.dg -= 1
    if st.dg >= 0:
        _bump_pattern(st, fast=False)
        st.phase = "WAIT_TRACK_IMPROVE"
        return 0.1

    st.phase = "MOTION_LOOP_SETUP"
    return 0.0


# =============================================================================
# Ablauf‑Helfer
# =============================================================================

def _ensure_markers(st: _State) -> None:
    if run_detect_once is not None:
        was_locked = bool(st.context.scene.get(_LOCK_KEY, False))
        if was_locked:
            try:
                st.context.scene[_LOCK_KEY] = False
            except Exception:
                was_locked = False
        try:
            run_detect_once(st.context, start_frame=st.origin_frame, handoff_to_pipeline=False)
        except Exception as ex:
            print(f"[Optimize] Detect pass failed: {ex}")
        finally:
            if was_locked:
                try:
                    st.context.scene[_LOCK_KEY] = True
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
    _delete_selected_tracks(st.context)
    print(f"[Optimize] Track‑Run beendet (pt={st.pt:.1f}, sus={st.sus:.1f}).")

def _apply_best_and_finish(st: _State) -> None:
    _set_flag2_motion_model(st.clip, st.mov)
    _set_flag3_channels(st.clip, st.vf)
    print(f"[Optimize] Fertig. ev={st.ev:.3f}, Motion={st.mov}, Channels={st.vf}, pt≈{st.ptv:.1f}")

    # NEU: Marker-Helper direkt ausführen
    try:
        from .marker_helper_main import marker_helper_main
        marker_helper_main(st.context)
        print("[Optimize] marker_helper_main direkt nach Optimizer ausgeführt.")
    except Exception as ex_func:
        print(f"[Optimize] WARN: marker_helper_main function failed: {ex_func!r}")
        try:
            import bpy
            bpy.ops.clip.marker_helper_main('INVOKE_DEFAULT')
            print("[Optimize] marker_helper_main Operator-Fallback ausgeführt.")
        except Exception as ex_op:
            print(f"[Optimize] WARN: marker_helper_main launch failed: {ex_op!r}")

    try:
        st.context.scene[_LOCK_KEY] = False  # Safety: etwaige Detect-Locks freigeben
    except Exception:
        pass
    globals()["_RUNNING"] = None

# =============================================================================
# Komfort‑Alias (kein Operator!)
# =============================================================================

def optimize_now(context: bpy.types.Context) -> None:
    start_optimization(context)


# =============================================================================
# Interne Minimal‑Tests (rein Python, ohne Blender‑Operatoren)
# =============================================================================

def _noop(*a, **k):
    return None


def run_internal_tests() -> None:
    print("[OptimizeTest] start")
    g = globals()
    _orig_set_flag1 = g.get("_set_flag1")
    _orig_ensure = g.get("_ensure_markers")
    _orig_start = g.get("_start_track")
    g["_set_flag1"] = _noop
    g["_ensure_markers"] = _noop
    g["_start_track"] = _noop

    try:
        class _StubClip:
            class _S: ...
            def __init__(self):
                self.tracking = type("T", (), {})()
                self.tracking.settings = self._S()
                self.tracking.objects = []
        stub_clip = _StubClip()
        st = _State(context=bpy.context, clip=stub_clip, origin_frame=1)

        st.ev = 10.0; st.dg = 0; st.pt = 21.0; st.ptv = 21.0; st.sus = 42.0; st.phase = "WAIT_TRACK_IMPROVE"
        _branch_ev_known(st, 11.0)
        assert abs(st.ev - 11.0) < 1e-6 and st.dg == 4 and abs(st.ptv - 21.0) < 1e-6 and st.phase == "WAIT_TRACK_IMPROVE"

        st.ev = 10.0; st.pt = 30.0; st.ptv = 25.0; st.rep_same_pt = 0; st.dg = 0; st.phase = "WAIT_TRACK_IMPROVE"
        _branch_ev_known(st, 8.5)
        assert st.rep_same_pt == 1 and st.phase == "WAIT_TRACK_IMPROVE"
        _branch_ev_known(st, 8.4)
        assert st.rep_same_pt == 2
        _branch_ev_known(st, 8.3)
        assert st.rep_same_pt == 0 and st.phase == "MOTION_LOOP_SETUP"

        st.ev = 10.0; st.dg = 1; st.pt = 21.0; st.rep_same_pt = 0; st.phase = "WAIT_TRACK_IMPROVE"
        _branch_ev_known(st, 9.9)
        assert st.dg == 0 and st.phase == "WAIT_TRACK_IMPROVE"

        # Kein Ergebnis → sollte nicht abbrechen, sondern Pattern bumpen
        st.ev = 10.0; st.dg = 0; st.pt = 21.0; st.phase = "WAIT_TRACK_IMPROVE"
        _branch_ev_known(st, 0.0)
        assert st.phase == "WAIT_TRACK_IMPROVE" and st.pt > 21.0

        print("[OptimizeTest] OK")
    finally:
        g["_set_flag1"] = _orig_set_flag1
        g["_ensure_markers"] = _orig_ensure
        g["_start_track"] = _orig_start
