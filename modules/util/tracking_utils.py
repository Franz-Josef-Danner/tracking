"""Utility helpers for Blender tracking."""

from __future__ import annotations

import bpy

from .context_helpers import get_clip_editor_override


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
            override = get_clip_editor_override(context)
            area = override.get("area")
            region = override.get("region")
            if area and region:
                clip_editor_found = True
                space = override.get("space_data", getattr(area, "spaces", None))
                if hasattr(space, "active"):
                    space = space.active if getattr(space, "active", None) else space
                if hasattr(track, "select"):
                    track.select = True
                tracks.active = track
                override["clip"] = clip
                with context.temp_override(**override):
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

        if ref_tracks is None:
            context_clip = getattr(getattr(bpy.context, "space_data", None), "clip", None)
            data_movieclips = getattr(bpy.data, "movieclips", None)
            movieclip_iter = []
            if data_movieclips is not None:
                if hasattr(data_movieclips, "values"):
                    movieclip_iter = data_movieclips.values()
                else:
                    movieclip_iter = data_movieclips
            fallback_sources = [
                (context_clip, "context clip"),
            ] + [(mc, "bpy.data.movieclips") for mc in movieclip_iter]

            removed_via_fallback = False
            for candidate_clip, label in fallback_sources:
                candidate_tracks = getattr(getattr(candidate_clip, "tracking", None), "tracks", None)
                if candidate_tracks and hasattr(candidate_tracks, "remove"):
                    target = None
                    if hasattr(candidate_tracks, "get"):
                        target = candidate_tracks.get(track.name)
                    if target is None:
                        for t in candidate_tracks:
                            if getattr(t, "name", None) == getattr(track, "name", None):
                                target = t
                                break
                    if target is not None:
                        try:
                            candidate_tracks.remove(target)
                            if logger:
                                logger.info(f"Removed NEW_ track via {label} fallback: {track.name}")
                            removed_via_fallback = True
                            break
                        except Exception as exc:  # pragma: no cover - fallback
                            if logger:
                                logger.warning(f"{label} fallback removal failed for {track.name}: {exc}")
                            break

            if removed_via_fallback:
                continue

        if ref_tracks and getattr(track, "name", None) in ref_tracks:
            try:
                ref_tracks.remove(ref_tracks.get(track.name))
                if logger:
                    logger.info(f"Force removed track by id_data: {track.name}")
                continue
            except Exception as exc:  # pragma: no cover - fallback
                if logger:
                    logger.warning(f"Fallback removal failed for {track.name}: {exc}")

        for t in ref_tracks or []:
            if getattr(t, "name", None) == getattr(track, "name", None):
                try:
                    ref_tracks.remove(t)
                    if logger:
                        logger.info(f"Removed NEW_ track by name match: {track.name}")
                    break
                except Exception as exc:  # pragma: no cover - fallback
                    if logger:
                        logger.warning(
                            f"Could not remove {track.name} by name match: {exc}"
                        )
                        failed.append(track.name)
                else:
                    break
        else:
            removed = False
            for other_clip in getattr(getattr(bpy, "data", None), "movieclips", []):
                other_tracks = getattr(getattr(other_clip, "tracking", None), "tracks", None)
                if not other_tracks:
                    continue
                t = (
                    other_tracks.get(track.name)
                    if hasattr(other_tracks, "get")
                    else None
                )
                if t and safe_remove_track(other_clip, t, logger=logger):
                    if logger:
                        logger.info(
                            f"Removed NEW_ track from other clip {getattr(other_clip, 'name', '')}: {track.name}"
                        )
                    removed = True
                    break
            if not removed:
                failed.append(track.name)

    try:  # ensure view layer refresh
        bpy.context.view_layer.update()
    except Exception:  # pragma: no cover - update might not be available in tests
        pass

    if failed and logger:
        logger.warning(f"{len(failed)} NEW_ tracks could not be removed: {failed}")

    return failed

