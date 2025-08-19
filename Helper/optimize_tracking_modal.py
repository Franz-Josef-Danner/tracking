"""Blender-Add-on – funktionaler Optimierungs‑Flow (keine Operatoren)

Ziel
----
Die funktionale Portierung der alten, bewährten Optimierung in eine reine
Funktions‑API. Es gibt **keine** Operatoren in diesem Modul. Stattdessen werden
Timer‑Callbacks (``bpy.app.timers``) benutzt, um nicht-blockierend zu arbeiten.

Vorgaben des Nutzers
--------------------
• Regel 1: kein Operator, nur Funktionen zum Aufrufen.
• Die Aufrufe für Detect & Track bleiben identisch zur neuen Version
  (d. h. wir verwenden dieselben Helper‑Funktionen wie dort).

Pseudo‑Code (vereinfacht übertragen)
------------------------------------

    default setzen: pt = Pattern Size, sus = Search Size
    flag1 setzen (Pattern/Search übernehmen)
    Marker setzen
    track → für jeden Track: f_i = Frames pro Track, e_i = Error → eg_i = f_i / e_i
    ega = Σ eg_i
    if ev < 0:
        ev = ega; pt *= 1.1; sus = pt*2; flag1
    else:
        if ega > ev:
            ev = ega; dg = 4; ptv = pt; pt *= 1.1; sus = pt*2; flag1
        else:
            dg -= 1
            if dg >= 0:
                pt *= 1.1; sus = pt*2; flag1
            else:
                // Motion‑Model‑Schleife (0..4)
                Pattern size = ptv; Search = ptv*2; flag2 setzen
                marker setzen; tracken; … → beste Motion wählen
                // Channel‑Schleife (vv 0..3), R/G/B‑Kombis laut Vorgabe

API‑Überblick
-------------
• ``start_optimization(context)`` – öffentlicher Einstieg, startet Ablauf.
• ``cancel_optimization()`` – bricht ggf. laufende Optimierung ab.
• Ablauf läuft über ``bpy.app.timers`` und setzt intern Status/Token.

Abhängigkeiten (Helper)
-----------------------
Wir verwenden dieselben Helper-Funktionen wie in der neuen Version:
• ``detect.run_detect_once(context, start_frame: int, handoff_to_pipeline=False)``
• ``tracking_helper.track_to_scene_end_fn(context, coord_token: str, start_frame: int, ...)``

Beide werden dynamisch importiert; fehlen sie, wird sauber abgebrochen.

Hinweis: Dieses Modul ist bewusst selbsterklärend und ausführlich kommentiert,
um die Logik später leicht anpassen zu können.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable

import bpy

# -----------------------------------------------------------------------------
# Dynamische Helper‑Imports (gleichen Signaturen wie in optimize_tracking_modal_neu)
# -----------------------------------------------------------------------------
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

try:  # Marker‑Erstellung (aus altem System)
    from .detect import perform_marker_detection  # type: ignore
except Exception:  # pragma: no cover
    perform_marker_detection = None  # type: ignore

# -----------------------------------------------------------------------------
# Konfiguration & Mapping
# -----------------------------------------------------------------------------
MOTION_MODELS: List[str] = [
    "Perspective",   # 0 → R: True,  G: False, B: False
    "Affine",        # 1 → R: True,  G: True,  B: False
    "LocRotScale",   # 2 → R: False, G: True,  B: False
    "LocScale",      # 3 → R: False, G: True,  B: True
    "LocRot",        # 4 → R: False, G: False, B: True
]

# Channel‑Preset gemäß Vorgabe
# vv = 0..3 → (R,G,B) wie in der Pseudologik
CHANNEL_PRESETS = {
    0: (True, False, False),
    1: (True, True, False),
    2: (False, True, False),
    3: (False, True, True),
    # Hinweis: Die Pseudo‑Liste zeigt 5 Fälle (0..4) für Motion, aber 4 für Channels.
}

# -----------------------------------------------------------------------------
# Hilfsfunktionen: Flags / Defaults setzen
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
# Metriken: EGA = Σ (frames_per_track / error_per_track)
# -----------------------------------------------------------------------------

def _calc_track_quality_sum(context: bpy.types.Context, clip: bpy.types.MovieClip) -> float:
    total = 0.0
    for ob in clip.tracking.objects:
        for tr in ob.tracks:
            err = None
            if error_value is not None:
                try:
                    # Variante A: (context, track)
                    err = float(error_value(context, tr))  # type: ignore[misc]
                except TypeError:
                    try:
                        # Variante B: (scene) – nutzt selektierte Marker; wir selektieren kurz den Track
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



# -----------------------------------------------------------------------------
# Detect + Track orchestration (nicht blockierend) via WindowManager‑Token
# -----------------------------------------------------------------------------
@dataclass
class _AsyncTracker:
    context: bpy.types.Context
    origin_frame: int
    token: str = field(default_factory=lambda: f"bw_optimize_token_{id(object())}")

    def start(self) -> None:
        assert track_to_scene_end_fn is not None, "tracking_helper fehlt"
        # altes Token ggf. räumen
        wm = self.context.window_manager
        if wm.get("bw_tracking_done_token", None) == self.token:
            del wm["bw_tracking_done_token"]
        # Start
        track_to_scene_end_fn(
            self.context,
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
# Hauptzustand der Optimierung (entspricht Pseudo‑Logik)
# -----------------------------------------------------------------------------
@dataclass
class _State:
    context: bpy.types.Context
    clip: bpy.types.MovieClip
    origin_frame: int

    # Dynamik
    ev: float = -1.0  # bester bisheriger Score
    dg: int = 0       # Degression‑Zähler
    pt: float = 21.0  # Pattern Size
    ptv: float = 21.0 # Pattern Size (Vorhalte)
    sus: float = 42.0 # Search Size (≈ 2*pt)

    mo_index: int = 0  # Motion‑Model‑Index (0..4)
    mov: int = 0       # bestes Motion‑Model

    vv: int = 0        # Channel‑Preset‑Index (0..3)
    vf: int = 0        # bestes Channel‑Preset

    phase: str = "INIT"
    tracker: Optional[_AsyncTracker] = None


# -----------------------------------------------------------------------------
# Steuerlogik als Timer‑Pipeline
# -----------------------------------------------------------------------------

_RUNNING: Optional[_State] = None


def start_optimization(context: bpy.types.Context) -> None:
    """Öffentlicher Einstieg: startet die nicht‑blockierende Optimierung.

    Kann mehrfach aufgerufen werden; ein bestehender Lauf wird vorher beendet.
    """
    cancel_optimization()

    space = getattr(context, "space_data", None)
    if not space or getattr(space, "type", "") != "CLIP_EDITOR":
        print("[Optimize] WARN: Kein CLIP_EDITOR aktiv – fahre trotzdem fort.")

    clip = getattr(space, "clip", None) or getattr(context.space_data, "clip", None)
    if not clip:
        raise RuntimeError("Kein aktiver Movie Clip.")

    st = _State(context=context, clip=clip, origin_frame=int(context.scene.frame_current))
    st.phase = "FLAG1_INIT"
    globals()["_RUNNING"] = st

    bpy.app.timers.register(_timer_step, first_interval=0.2)
    print(f"[Optimize] Start @frame={st.origin_frame}")


def cancel_optimization() -> None:
    global _RUNNING
    _RUNNING = None


# ---------------------- Timer‑Step ----------------------

def _timer_step() -> float | None:
    st = globals().get("_RUNNING")
    if not st:
        return None

    try:
        if st.phase == "FLAG1_INIT":
            # Defaults setzen + Marker erzeugen + erster Track
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _ensure_markers(st)
            _start_track(st)
            st.phase = "WAIT_TRACK_BASE"
            return 0.1

        if st.phase == "WAIT_TRACK_BASE":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            if st.ev < 0:
                st.ev = ega
                st.pt *= 1.1
                st.sus = st.pt * 2
                _set_flag1(st.clip, int(st.pt), int(st.sus))
                _start_track(st)
                st.phase = "WAIT_TRACK_IMPROVE"
                return 0.1
            else:
                return _branch_ev_known(st, ega)

        if st.phase == "WAIT_TRACK_IMPROVE":
            if not st.tracker or not st.tracker.done():
                return 0.1
            _finish_track(st)
            ega = _calc_track_quality_sum(st.context, st.clip)
            return _branch_ev_known(st, ega)

        if st.phase == "MOTION_LOOP_SETUP":
            # Setze pt := ptv, sus := ptv*2
            st.pt = st.ptv
            st.sus = st.pt * 2
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            st.mo_index = 0
            st.mov = 0
            st.phase = "MOTION_LOOP_RUN"
            return 0.0

        if st.phase == "MOTION_LOOP_RUN":
            if st.mo_index >= 5:
                # Motion abgeschlossen → Channel‑Loop
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
            if ega > st.ev:
                st.ev = ega
                st.mov = st.mo_index
            st.mo_index += 1
            st.phase = "MOTION_LOOP_RUN"
            return 0.0

        if st.phase == "CHANNEL_LOOP_RUN":
            if st.vv >= 4:
                # Channel‑Schleife fertig → bestes anwenden & Finish
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
            if ega > st.ev:
                st.ev = ega
                st.vf = st.vv
            st.vv += 1
            st.phase = "CHANNEL_LOOP_RUN"
            return 0.0

        # Unbekannte Phase → abbrechen
        print(f"[Optimize] Unbekannte Phase: {st.phase}")
        globals()["_RUNNING"] = None
        return None

    except Exception as ex:  # noqa: BLE001
        print(f"[Optimize] Fehler: {ex}")
        globals()["_RUNNING"] = None
        return None


# ---------------------- Branch‑Helfer ----------------------

def _branch_ev_known(st: _State, ega: float) -> float:
    if ega > st.ev:
        st.ev = ega
        st.dg = 4
        st.ptv = st.pt
        st.pt *= 1.1
        st.sus = st.pt * 2
        _set_flag1(st.clip, int(st.pt), int(st.sus))
        _start_track(st)
        st.phase = "WAIT_TRACK_IMPROVE"
        return 0.1
    else:
        st.dg -= 1
        if st.dg >= 0:
            st.pt *= 1.1
            st.sus = st.pt * 2
            _set_flag1(st.clip, int(st.pt), int(st.sus))
            _start_track(st)
            st.phase = "WAIT_TRACK_IMPROVE"
            return 0.1
        else:
            st.phase = "MOTION_LOOP_SETUP"
            return 0.0


# ---------------------- Ablauf‑Helfer ----------------------

def _ensure_markers(st: _State) -> None:
    # Immer den robusten Detect‑Pass nutzen (Signatur passt zur neuen Version)
    if run_detect_once is not None:
        try:
            run_detect_once(st.context, start_frame=st.origin_frame, handoff_to_pipeline=False)
        except Exception:
            pass
    else:
        # Alternativ: Detect‑Pass (wie neue Version)
        if run_detect_once is not None:
            try:
                run_detect_once(st.context, start_frame=st.origin_frame, handoff_to_pipeline=False)
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
    # Playhead-Reset sicherstellen
    cur = int(st.context.scene.frame_current)
    if cur != st.origin_frame:
        try:
            st.context.scene.frame_set(st.origin_frame)
        except Exception:
            st.context.scene.frame_current = st.origin_frame


def _apply_best_and_finish(st: _State) -> None:
    # bestes Motion‑Model anwenden
    _set_flag2_motion_model(st.clip, st.mov)
    # bestes Channel‑Preset anwenden
    _set_flag3_channels(st.clip, st.vf)

    print(
        f"[Optimize] Fertig. ev={st.ev:.3f}, Motion={st.mov}, Channels={st.vf}, pt≈{st.ptv:.1f}"
    )

    globals()["_RUNNING"] = None


# -----------------------------------------------------------------------------
# Optionale Komfort‑Funktion für UI‑Buttons (kein Operator!)
# -----------------------------------------------------------------------------

def optimize_now(context: bpy.types.Context) -> None:
    """Bequemer Alias – kann z.B. in einem Panel‑Draw‑Callback aufgerufen werden."""
    start_optimization(context)
