"""Utility helpers for Blender tracking."""

from __future__ import annotations

import bpy


def _track_exists(tracks, track):
    """Return ``True`` if ``track`` is present in ``tracks``."""
    try:
        if track in tracks:
            return True
    except TypeError:
        pass

    name = getattr(track, "name", None)
    if name is None:
        return False

    try:
        if name in tracks:
            return True
    except TypeError:
        pass

    if hasattr(tracks, "get"):
        return tracks.get(name) is not None

    return any(getattr(t, "name", None) == name for t in tracks)


def safe_remove_track(clip, track, logger=None):
    """Safely remove ``track`` from ``clip``.

    Tries to call :func:`bpy.ops.clip.track_remove` in a Clip Editor UI
    context. If the operator cannot be executed, falls back to directly
    removing the track from ``clip.tracking.tracks``. Returns ``True`` when
    the track no longer exists after the attempt, otherwise ``False``.
    """
    tracks = None

    if clip is not None and hasattr(clip, "tracking"):
        tracks = clip.tracking.tracks
    elif hasattr(clip, "remove") and hasattr(clip, "active"):
        tracks = clip
    
    if tracks is None and hasattr(track, "id_data"):
        parent = track.id_data
        if hasattr(parent, "tracking"):
            tracks = parent.tracking.tracks
            clip = parent

    if tracks is None:
        return False

    try:
        op = bpy.ops.clip.track_remove
    except AttributeError:
        op = None

    clip_editor_found = False
    if op is not None:
        try:
            context = bpy.context
            area = next(
                (a for a in context.screen.areas if a.type == "CLIP_EDITOR"),
                None,
            )
            region = (
                next((r for r in area.regions if r.type == "WINDOW"), None)
                if area
                else None
            )
            if area and region:
                clip_editor_found = True
                space = area.spaces.active
                if hasattr(track, "select"):
                    track.select = True
                tracks.active = track
                with context.temp_override(
                    area=area, region=region, space_data=space, clip=clip
                ):
                    op()
        except Exception:  # pragma: no cover - fallback
            pass
    if op is not None and not clip_editor_found and logger:
        logger.warning("No CLIP_EDITOR area found; falling back to direct removal")

    still_there = _track_exists(tracks, track)
    if still_there and hasattr(tracks, "remove"):
        try:
            tracks.remove(track)
        except Exception as exc:  # pragma: no cover - fallback
            if logger:
                logger.warning(f"Track remove fallback failed for {track.name}: {exc}")

    still_there = _track_exists(tracks, track)
    if still_there and logger:
        logger.warning(f"Track '{track.name}' still exists after attempted removal!")
    return not still_there


def count_markers_in_frame(tracks, frame):
    """Return the number of markers on ``frame`` across ``tracks``.

    Parameters
    ----------
    tracks : iterable
        Collection of tracks containing marker lists.
    frame : int
        The frame for which markers should be counted.

    Returns
    -------
    int
        Number of tracks that have at least one marker on ``frame``.
    """

    count = 0
    for track in tracks:
        try:
            markers = track.markers
        except AttributeError:
            continue
        if any(getattr(m, "frame", None) == frame for m in markers):
            count += 1
    return count


def hard_remove_new_tracks(clip, logger=None):
    """Robustly remove all tracks starting with ``NEW_``.

    Returns a list of track names that could not be removed.
    """

    if not getattr(clip, "tracking", None):
        return ["clip has no tracking data"]

    tracks = clip.tracking.tracks
    all_tracks = list(tracks)
    failed = []

    for track in all_tracks:
        if not getattr(track, "name", "").startswith("NEW_"):
            continue

        removed = safe_remove_track(clip, track, logger=logger)
        if removed:
            continue

        ref_clip = getattr(track, "id_data", clip)
        ref_tracks = getattr(getattr(ref_clip, "tracking", None), "tracks", None)

        if hasattr(ref_tracks, "get") and hasattr(ref_tracks, "remove"):
            try:
                target = ref_tracks.get(track.name)
                if target:
                    ref_tracks.remove(target)
                    if logger:
                        logger.info(f"Force removed track by id_data: {track.name}")
                    continue
            except Exception as exc:  # pragma: no cover - fallback
                if logger:
                    logger.warning(f"Fallback removal failed for {track.name}: {exc}")

        if hasattr(ref_tracks, "__iter__") and hasattr(ref_tracks, "remove"):
            for t in ref_tracks:
                if getattr(t, "name", None) == getattr(track, "name", None):
                    try:
                        ref_tracks.remove(t)
                        if logger:
                            logger.info(f"Removed NEW_ track by name match: {track.name}")
                        break
                    except Exception as exc:  # pragma: no cover - fallback
                        if logger:
                            logger.warning(f"Could not remove {track.name} by name match: {exc}")
                        failed.append(track.name)
                        break
            else:
                failed.append(track.name)
        else:
            if logger:
                logger.warning(f"ref_tracks not removable or iterable for {track.name}")
            failed.append(track.name)

    try:  # ensure view layer refresh
        bpy.context.view_layer.update()
    except Exception:  # pragma: no cover - update might not be available in tests
        pass

    if failed and logger:
        logger.warning(f"{len(failed)} NEW_ tracks could not be removed: {failed}")

    return failed
