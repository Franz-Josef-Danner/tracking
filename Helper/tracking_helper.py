# SPDX-License-Identifier: GPL-2.0-or-later
"""
Helper/tracking_helper.py – mit ausführlichen Konsolen‑Logs (FIXED)

✔ Regel 1: **Kein eigener Operator**, nur Funktions‑API
✔ Regel 2: **Nur vorwärts** tracken
✔ Regel 3: `INVOKE_DEFAULT`, `backwards=False`, `sequence=True`
✔ Regel 4: **Playhead** nach dem Tracken **zurück** auf Ursprungs‑Frame

Zusätzlich:
- Behebt `SyntaxError` durch Entfernen eines versehentlich stehen gebliebenen Funktionsfragments.
- Robustere UI‑Aktualisierung ohne `bpy.ops.anim.change_frame` (verursachte Kontext‑Fehler), stattdessen
  `scene.frame_set(...)` + `region.tag_redraw()` auf allen CLIP‑Editor‑Fenstern.
- Watch‑Loop hält den Playhead auf dem Ursprungs‑Frame, bis er 2 Ticks stabil ist.

Log‑Präfix: "[BW-Track]"
"""
from __future__ import annotations

from typing import Optional, Tuple

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
    "_test_reset_only",  # einfache Selbsttests
)

LOG_PREFIX = "[BW-Track]"


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"{LOG_PREFIX} {msg}")


def _iter_clip_areas():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                yield window, area


def _iter_clip_spaces():
    """Liefert (window, area, space) Triplets für aktive CLIP_EDITOR‑Spaces."""
    for window, area in _iter_clip_areas():
        space = area.spaces.active if hasattr(area, "spaces") else None
        if space and getattr(space, "clip_user", None) is not None:
            yield window, area, space


def _get_active_clip_in_area(area: bpy.types.Area) -> Optional[bpy.types.MovieClip]:
    space = area.spaces.active if hasattr(area, "spaces") else None
    if space and getattr(space, "clip", None) is not None:
        return space.clip
    return None


def _get_any_clip() -> Optional[bpy.types.MovieClip]:
    for _w, area in _iter_clip_areas():
        clip = _get_active_clip_in_area(area)
        if clip is not None:
            return clip
    return None


def _redraw_clip_editors(_context: bpy.types.Context | None = None) -> None:
    """Force‑Redraw aller Clip‑Editoren."""
    for _w, area in _iter_clip_areas():
        for region in area.regions:
            if region.type == 'WINDOW':
                region.tag_redraw()

def _log(msg: str) -> None:
    print(f"{LOG_PREFIX} {msg}")


def _iter_clip_areas():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                yield window, area


def _get_active_clip_in_area(area: bpy.types.Area) -> Optional[bpy.types.MovieClip]:
    space = area.spaces.active if hasattr(area, "spaces") else None
    if space and getattr(space, "clip", None) is not None:
        return space.clip
    return None


def _get_any_clip() -> Optional[bpy.types.MovieClip]:
    for _w, area in _iter_clip_areas():
        clip = _get_active_clip_in_area(area)
        if clip is not None:
            return clip
    return None


def _redraw_clip_editors(_context: bpy.types.Context | None = None) -> None:
    """Force‑Redraw aller Clip‑Editoren."""
    for _w, area in _iter_clip_areas():
        for region in area.regions:
            if region.type == 'WINDOW':
                region.tag_redraw()


def _set_frame_and_notify(frame: int, *, verbose: bool = True) -> None:
    """Setzt **Szenen‑Frame** und **Editor‑Anzeige‑Frame** auf `frame` und redrawt.

    WICHTIG: Der Movie‑Clip‑Editor nutzt eine eigene Anzeige‑Position über
    `space.clip_user.frame_current`. Wenn nur `scene.frame_set(...)` benutzt wird,
    kann der Viewer sichtbar auf einem anderen Frame stehen bleiben. Daher setzen wir beides.
    """
    scene = bpy.context.scene
    if verbose:
        _log(f"Reset versuch: scene.frame_set({frame}) – vorher: {scene.frame_current}")
    try:
        scene.frame_set(frame)
    except Exception as ex:
        _log(f"scene.frame_set Exception: {ex!r} – fallback scene.frame_current = {frame}")
        scene.frame_current = frame

    # Zusätzlich: alle CLIP‑Editoren auf frame schalten
    for _window, area, space in _iter_clip_spaces():
        try:
            user = space.clip_user
            before = int(getattr(user, 'frame_current', -1))
            user.frame_current = int(frame)
            after = int(getattr(user, 'frame_current', -1))
            if verbose:
                _log(f"Editor {area.as_pointer()}: clip_user.frame_current {before} → {after}")
        except Exception as ex:
            _log(f"Editor {area.as_pointer()}: set clip_user.frame_current Exception: {ex!r}")

    _redraw_clip_editors(None)
    if verbose:
        _log(f"Reset fertig – Szene: {scene.frame_current}")


def _furthest_tracked_frame(clip: bpy.types.MovieClip) -> int:
    """Ermittle den maximalen Marker‑Frame im Clip (Diagnose).

    FIX: korrekte Einrückung (vorheriger IndentationError in der for‑Schleife).
    """
    mx = 0
    try:
        for tr in getattr(clip.tracking, "tracks", []):
            for m in getattr(tr, "markers", []):
                f = int(getattr(m, "frame", 0))
                if f > mx:
                    mx = f
    except Exception as ex:
        _log(f"_furthest_tracked_frame Exception: {ex!r}")
    return mx(clip: bpy.types.MovieClip) -> int:
    """Ermittle den maximalen Marker‑Frame im Clip (Diagnose).

    FIX: korrekte Einrückung (vorheriger IndentationError in der for‑Schleife).
    """
    mx = 0
    try:
        for tr in getattr(clip.tracking, "tracks", []):
            for m in getattr(tr, "markers", []):
                f = int(getattr(m, "frame", 0))
                if f > mx:
                    mx = f
    except Exception as ex:
        _log(f"_furthest_tracked_frame Exception: {ex!r}")
    return mx


# -----------------------------------------------------------------------------
# Kern‑Helper: vorwärts tracken (INVOKE, sequence) → *nächster Tick* Frame‑Reset
# -----------------------------------------------------------------------------

def _start_forward_tracking_invoke(context: bpy.types.Context) -> Tuple[bool, str]:
    try:
        res = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        _log(f"track_markers INVOKE aufgerufen → result={res}")
        return True, f"track_markers INVOKE → {res}"
    except Exception as ex:  # noqa: BLE001
        _log(f"track_markers INVOKE Exception: {ex!r}")
        return False, f"Track‑Fehler: {ex}"


def track_to_scene_end_fn(
    context: bpy.types.Context,
    *,
    coord_token: Optional[str] = None,
    start_frame: Optional[int] = None,
    debug: bool = True,
    watch_interval: float = 0.2,
    watch_stable_ticks: int = 2,
    first_delay: float = 0.25,
) -> None:
    """Nur‑Vorwärts‑Tracking (INVOKE, sequence) und **danach** Playhead‑Reset.

    - Kein eigener Operator (Regel 1)
    - Nur vorwärts (Regel 2)
    - INVOKE_DEFAULT, backwards=False, sequence=True (Regel 3)
    - Playhead‑Reset auf Ursprungs‑Frame (Regel 4)

    Mit **Debug‑Logs**, Frame‑**Progress‑Probe** und einer Watch‑Loop.
    """
    wm = context.window_manager
    scene = context.scene

    areas = list(_iter_clip_areas())
    if debug:
        _log(f"Gefundene CLIP_EDITOR Areas: {len(areas)}")
    clip = _get_any_clip()
    if clip is None:
        _log("Kein aktiver MovieClip gefunden – Abbruch")
        raise RuntimeError("Kein aktiver MovieClip im CLIP_EDITOR gefunden.")
    if debug:
        _log(f"Clip Name: {getattr(clip,'name','<unnamed>')}")

    # Startframe bestimmen
    if start_frame is not None:
        try:
            origin_frame = int(start_frame)
        except Exception:
            origin_frame = int(scene.frame_current)
        else:
            origin_frame = max(int(scene.frame_start), min(int(scene.frame_end), origin_frame))
    else:
        origin_frame = int(scene.frame_current)
    if debug:
        _log(f"Origin Frame: {origin_frame} (source={'param' if start_frame is not None else 'scene'})")
        _log(f"Vor Start: furthest_tracked={_furthest_tracked_frame(clip)}")

    # Progress‑Probe: misst, ob sich der Szenen‑Frame *während* INVOKE bewegt
    probe = {
        "changes": 0,
        "max_seen": origin_frame,
        "last": origin_frame,
        "done": False,
    }

    def _probe_progress() -> Optional[float]:
        if probe["done"]:
            return None
        cur = int(bpy.context.scene.frame_current)
        if cur != probe["last"]:
            probe["changes"] += 1
            probe["last"] = cur
            if cur > probe["max_seen"]:
                probe["max_seen"] = cur
            if debug:
                _log(f"[Probe] scene.frame_current bewegt → {cur} (changes={probe['changes']}, max_seen={probe['max_seen']})")
        return 0.1

    bpy.app.timers.register(_probe_progress, first_interval=0.1)

    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        probe["done"] = True
        raise RuntimeError(info)

    # Diagnose + erster Reset nach kleinem Delay --------------------------------
    def _tick_once() -> Optional[float]:
        if debug:
            _log("Timer Tick #1 – versuche Reset auf Origin")
            _log(
                f"Tick #1 Diagnose: scene.frame_current={int(bpy.context.scene.frame_current)}, "
                f"furthest_tracked={_furthest_tracked_frame(clip)}"
            )
        before = int(bpy.context.scene.frame_current)
        _set_frame_and_notify(origin_frame, verbose=debug)
        after = int(bpy.context.scene.frame_current)
        if debug:
            _log(f"Timer Tick #1 – Frame vorher={before}, nachher={after}")
        # Starte Watch‑Loop, die den Playhead hält, bis Stabilität erkannt ist
        bpy.app.timers.register(_watch_reset, first_interval=watch_interval)
        return None

    # Watch‑Loop: Playhead bis Stabilität halten --------------------------------
    state = {"stable": 0}

    def _watch_reset() -> Optional[float]:
        # Szene prüfen
        cur_scene = int(bpy.context.scene.frame_current)
        # Alle Editor‑Frames einsammeln
        editor_frames = []
        for _w, area, space in _iter_clip_spaces():
            try:
                editor_frames.append((int(space.clip_user.frame_current), area.as_pointer()))
            except Exception:
                editor_frames.append((None, area.as_pointer()))
        if debug:
            _log(f"Watch: scene={cur_scene}, editors={[f for f,_ in editor_frames]}")

        # Stabilitätslogik: Szene **und** alle Editor‑Frames müssen == origin sein
        all_ok = (cur_scene == origin_frame) and all(f == origin_frame for f, _ in editor_frames if f is not None)
        if all_ok:
            state["stable"] += 1
        else:
            state["stable"] = 0
            # Korrigieren, wo nötig
            if cur_scene != origin_frame:
                _log(f"Watch: Szene != origin ({cur_scene} != {origin_frame}) → setze Szene")
                _set_frame_and_notify(origin_frame, verbose=False)
            for f, aptr in editor_frames:
                if f is None:
                    continue
                if f != origin_frame:
                    _log(f"Watch: Editor {aptr} != origin ({f} != {origin_frame}) → setze Editor")
                    # Nur Editor‑Frame setzen, Szene belassen
                    try:
                        for __w, area2, space2 in _iter_clip_spaces():
                            if area2.as_pointer() == aptr:
                                space2.clip_user.frame_current = int(origin_frame)
                    except Exception as ex:
                        _log(f"Watch: Editor {aptr} set Exception: {ex!r}")
            _redraw_clip_editors(None)

        if state["stable"] >= watch_stable_ticks:
            probe["done"] = True
            # Abschluss‑Summary inkl. Editor‑Frames
            if debug:
                _log(
                    f"Summary: probe.changes={probe['changes']}, probe.max_seen={probe['max_seen']}, "
                    f"furthest_tracked={_furthest_tracked_frame(clip)}, editors_final={[f for f,_ in editor_frames]}"
                )
            if coord_token:
                wm["bw_tracking_done_token"] = coord_token
            wm["bw_tracking_last_info"] = {
                "start_frame": origin_frame,
                "tracked_until": int(bpy.context.scene.frame_current),
                "mode": "INVOKE",
                "note": info,
                "watch_stable": state["stable"],
                "probe_changes": probe["changes"],
                "probe_max_seen": probe["max_seen"],
                "editors_final": [f for f,_ in editor_frames],
            }
            if debug:
                _log("Watch: stabil erreicht → Token gesetzt, beende Watch & Probe")
            return None
        return watch_interval

    if debug:
        _log(f"Register Timer Tick #1 in {first_delay:.2f}s")
    bpy.app.timers.register(_tick_once, first_interval=first_delay)


# -----------------------------------------------------------------------------
# Einfache Selbsttests (innerhalb von Blender im Text‑Editor/Console aufrufbar)
# -----------------------------------------------------------------------------

def _test_reset_only(context: bpy.types.Context, *, delta: int = 5) -> None:
    """Kleiner Sanity‑Test für den Reset (Szene + Editors)."""
    scene = context.scene
    f0 = int(scene.frame_current)
    # Editor‑Frames vorher/nachher loggen
    before_editors = [ (int(s.clip_user.frame_current), a.as_pointer()) for _w,a,s in _iter_clip_spaces() ]
    scene.frame_set(f0 + int(delta))
    _set_frame_and_notify(f0, verbose=True)
    after_editors = [ (int(s.clip_user.frame_current), a.as_pointer()) for _w,a,s in _iter_clip_spaces() ]
    assert int(scene.frame_current) == f0, (
        f"Reset Szene fehlgeschlagen: erwartet {f0}, ist {int(scene.frame_current)}"
    )
    assert all(f == f0 for f,_ in after_editors), (
        f"Reset Editor(s) fehlgeschlagen: erwartet {[f0]*len(after_editors)}, ist {[f for f,_ in after_editors]} (vorher={before_editors})"
    )
    _log("_test_reset_only: OK (Szene + Editors)")


def _test_furthest_tracked_frame(context: bpy.types.Context) -> None:
    """Test: _furthest_tracked_frame liefert >= 0 und ist integer."""
    clip = _get_any_clip()
    if not clip:
        _log("_test_furthest_tracked_frame: Kein Clip → überspringe Test")
        return
    v = _furthest_tracked_frame(clip)
    assert isinstance(v, int) and v >= 0, f"unerwarteter Wert: {v!r}"
    _log(f"_test_furthest_tracked_frame: OK (wert={v})")


def _test_track_and_reset(context: bpy.types.Context) -> None:
    """Integrationstest: Startframe merken, Funktion ausführen, Startframe in Szene **und** Editors prüfen.

    Hinweis: setzt aktive Marker im Clip voraus, sonst trackt Blender nicht sichtbar vorwärts.
    """
    scene = context.scene
    f0 = int(scene.frame_current)
    track_to_scene_end_fn(context, start_frame=f0, debug=True, first_delay=0.2)
    def _assert_cb():
        editors = [ (int(getattr(s.clip_user,'frame_current',-1)), a.as_pointer()) for _w,a,s in _iter_clip_spaces() ]
        assert int(bpy.context.scene.frame_current) == f0, (
            f"Startframe‑Reset Szene fehlgeschlagen: erwartet {f0}, ist {int(bpy.context.scene.frame_current)}"
        )
        assert all(f == f0 for f,_ in editors), (
            f"Startframe‑Reset Editors fehlgeschlagen: erwartet {[f0]*len(editors)}, ist {[f for f,_ in editors]}"
        )
        _log("_test_track_and_reset: OK (Szene + Editors)")
        return None
    bpy.app.timers.register(_assert_cb, first_interval=0.6)
