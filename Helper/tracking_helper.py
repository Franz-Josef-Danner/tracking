# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

from typing import Optional

import bpy

__all__ = (
    "track_to_scene_end_fn",
    "_redraw_clip_editors",
    "_test_reset_only",
    "_test_furthest_tracked_frame",
    "_test_track_and_reset",
)

LOG_PREFIX = "[BW-Track]"

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _log(msg: str) -> None:
    pass

def _iter_clip_areas():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                yield window, area


def _iter_clip_spaces():
    """Yield (window, area, space) triplets for active CLIP_EDITOR spaces."""
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
    """Force‑redraw all Clip Editors."""
    for _w, area in _iter_clip_areas():
        for region in area.regions:
            if region.type == 'WINDOW':
                region.tag_redraw()


def _set_frame_and_notify(frame: int, *, verbose: bool = True) -> None:
    """Set scene frame **and** every Clip Editor's view frame to `frame`, then redraw.

    The Movie Clip editor has its own viewer frame (space.clip_user.frame_current). We set both.
    """
    scene = bpy.context.scene
    if verbose:
        _log(f"Reset attempt: scene.frame_set({frame}) – before: {scene.frame_current}")
    try:
        scene.frame_set(frame)
    except Exception as ex:
        _log(f"scene.frame_set Exception: {ex!r} – fallback scene.frame_current = {frame}")
        scene.frame_current = frame

    # Also set each editor's viewer frame
    for _window, area, space in _iter_clip_spaces():
        try:
            user = space.clip_user
            before = int(getattr(user, 'frame_current', -1))
            user.frame_current = int(frame)
            after = int(getattr(user, 'frame_current', -1))
            if verbose:
                aptr = getattr(area, 'as_pointer', lambda: 0)()
                _log(f"Editor {aptr}: clip_user.frame_current {before} → {after}")
        except Exception as ex:
            aptr = getattr(area, 'as_pointer', lambda: 0)()
            _log(f"Editor {aptr}: set clip_user.frame_current Exception: {ex!r}")

    _redraw_clip_editors(None)
    if verbose:
        _log(f"Reset done – scene now: {scene.frame_current}")


def _furthest_tracked_frame(clip: bpy.types.MovieClip) -> int:
    """Return the max marker.frame across all tracks (diagnostics)."""
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
# Forward tracking (INVOKE, sequence) → next tick: reset to origin
# -----------------------------------------------------------------------------

def _start_forward_tracking_invoke(context: bpy.types.Context) -> tuple[bool, str]:
    try:
        res = bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        _log(f"track_markers INVOKE called → result={res}")
        return True, f"track_markers INVOKE → {res}"
    except Exception as ex:  # noqa: BLE001
        _log(f"track_markers INVOKE Exception: {ex!r}")
        return False, f"Track error: {ex}"


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
    """Forward‑track (INVOKE, sequence) then force playhead back to the tracking origin.

    The reset is enforced both for the scene frame and for each Clip Editor's viewer frame.
    """
    wm = context.window_manager
    scene = context.scene

    areas = list(_iter_clip_areas())
    if debug:
        _log(f"Found CLIP_EDITOR areas: {len(areas)}")
    clip = _get_any_clip()
    if clip is None:
        _log("No active MovieClip in any CLIP_EDITOR – abort")
        raise RuntimeError("No active MovieClip in CLIP_EDITOR found.")
    if debug:
        _log(f"Clip Name: {getattr(clip,'name','<unnamed>')}")

    # Determine origin frame
    if start_frame is not None:
        try:
            origin_frame = int(start_frame)
        except Exception:
            origin_frame = int(scene.frame_current)
        else:
            origin_frame = max(int(scene.frame_start), min(int(scene.frame_end), origin_frame))
        origin_source = "param"
    else:
        origin_frame = int(scene.frame_current)
        origin_source = "scene"
    if debug:
        _log(f"Origin Frame: {origin_frame} (source={origin_source})")
        _log(f"Before start: furthest_tracked={_furthest_tracked_frame(clip)}")

    # Track progress probe (did scene frame move?)
    probe = {"changes": 0, "max_seen": origin_frame, "last": origin_frame, "done": False}

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
                _log(f"[Probe] scene frame moved → {cur} (changes={probe['changes']}, max_seen={probe['max_seen']})")
        return 0.1

    bpy.app.timers.register(_probe_progress, first_interval=0.1)

    ok, info = _start_forward_tracking_invoke(context)
    if not ok:
        probe["done"] = True
        raise RuntimeError(info)

    # First reset tick
    def _tick_once() -> Optional[float]:
        if debug:
            _log("Timer Tick #1 – reset to origin")
            _log(
                f"Tick #1 diag: scene.frame_current={int(bpy.context.scene.frame_current)}, "
                f"furthest_tracked={_furthest_tracked_frame(clip)}"
            )
        before = int(bpy.context.scene.frame_current)
        _set_frame_and_notify(origin_frame, verbose=debug)
        after = int(bpy.context.scene.frame_current)
        if debug:
            _log(f"Timer Tick #1 – scene before={before}, after={after}")
        # Start watch loop that keeps scene & editor frames pinned to origin until stable
        bpy.app.timers.register(_watch_reset, first_interval=watch_interval)
        return None

    # Watch loop
    state = {"stable": 0}

    def _watch_reset() -> Optional[float]:
        # Scene
        cur_scene = int(bpy.context.scene.frame_current)
        # Editors
        editor_frames: list[tuple[Optional[int], int]] = []
        for _w, area, space in _iter_clip_spaces():
            try:
                editor_frames.append((int(space.clip_user.frame_current), int(getattr(area, 'as_pointer', lambda: 0)())))
            except Exception:
                editor_frames.append((None, int(getattr(area, 'as_pointer', lambda: 0)())))
        if debug:
            _log(f"Watch: scene={cur_scene}, editors={[f for f,_ in editor_frames]}")

        # Stable if scene and all editors are at origin
        all_ok = (cur_scene == origin_frame) and all(
            (f == origin_frame) for f, _ in editor_frames if f is not None
        )
        if all_ok:
            state["stable"] += 1
        else:
            state["stable"] = 0
            # Correct discrepancies
            if cur_scene != origin_frame:
                _log(f"Watch: scene != origin ({cur_scene} != {origin_frame}) → set scene")
                _set_frame_and_notify(origin_frame, verbose=False)
            for f, aptr in editor_frames:
                if f is None:
                    continue
                if f != origin_frame:
                    _log(f"Watch: editor {aptr} != origin ({f} != {origin_frame}) → set editor")
                    try:
                        # Set only that editor's view frame
                        for __w, area2, space2 in _iter_clip_spaces():
                            if int(getattr(area2, 'as_pointer', lambda: 0)()) == aptr:
                                space2.clip_user.frame_current = int(origin_frame)
                    except Exception as ex:
                        _log(f"Watch: editor {aptr} set Exception: {ex!r}")
                    _redraw_clip_editors(None)

        if state["stable"] >= watch_stable_ticks:
            probe["done"] = True
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
                _log("Watch: stable reached → token set, stop watch & probe")
            return None
        return watch_interval

    if debug:
        _log(f"Register Timer Tick #1 in {first_delay:.2f}s")
    bpy.app.timers.register(_tick_once, first_interval=first_delay)

# -----------------------------------------------------------------------------
# Simple self tests (run inside Blender's console/text editor)
# -----------------------------------------------------------------------------

def _test_reset_only(context: bpy.types.Context, *, delta: int = 5) -> None:
    """Sanity check: scene & editor frames return to f0."""
    scene = context.scene
    f0 = int(scene.frame_current)
    before_editors = [ (int(s.clip_user.frame_current), getattr(a,'as_pointer',lambda:0)()) for _w,a,s in _iter_clip_spaces() ]
    scene.frame_set(f0 + int(delta))
    _set_frame_and_notify(f0, verbose=True)
    after_editors = [ (int(s.clip_user.frame_current), getattr(a,'as_pointer',lambda:0)()) for _w,a,s in _iter_clip_spaces() ]
    assert int(scene.frame_current) == f0, (
        f"Scene reset failed: expected {f0}, got {int(scene.frame_current)}"
    )
    assert all(f == f0 for f,_ in after_editors), (
        f"Editor reset failed: expected {[f0]*len(after_editors)}, got {[f for f,_ in after_editors]} (before={before_editors})"
    )
    _log("_test_reset_only: OK (scene + editors)")


def _test_furthest_tracked_frame(context: bpy.types.Context) -> None:
    clip = _get_any_clip()
    if not clip:
        _log("_test_furthest_tracked_frame: no clip → skip")
        return
    v = _furthest_tracked_frame(clip)
    assert isinstance(v, int) and v >= 0, f"unexpected value: {v!r}"
    _log(f"_test_furthest_tracked_frame: OK (value={v})")


def _test_track_and_reset(context: bpy.types.Context) -> None:
    """Integration: remember start frame, run flow, assert scene **and** editors at start."""
    scene = context.scene
    f0 = int(scene.frame_current)
    track_to_scene_end_fn(context, start_frame=f0, debug=True, first_delay=0.2)
    def _assert_cb():
        editors = [ (int(getattr(s.clip_user,'frame_current',-1)), getattr(a,'as_pointer',lambda:0)()) for _w,a,s in _iter_clip_spaces() ]
        assert int(bpy.context.scene.frame_current) == f0, (
            f"Startframe reset (scene) failed: expected {f0}, got {int(bpy.context.scene.frame_current)}"
        )
        assert all(f == f0 for f,_ in editors), (
            f"Startframe reset (editors) failed: expected {[f0]*len(editors)}, got {[f for f,_ in editors]}"
        )
        _log("_test_track_and_reset: OK (scene + editors)")
        return None
    bpy.app.timers.register(_assert_cb, first_interval=0.6)
