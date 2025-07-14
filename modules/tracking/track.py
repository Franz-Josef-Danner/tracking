"""Wrapper utilities for clip tracking."""

import bpy


def track_markers(context, forwards=True, backwards=True, logger=None):
    """Track markers in both directions based on arguments.

    Parameters
    ----------
    context : :class:`bpy.types.Context`
        Blender context used for the operator call.
    forwards : bool, optional
        Track forwards if ``True``.
    backwards : bool, optional
        Track backwards if ``True``.
    logger : :class:`TrackerLogger`, optional
        Logger instance for error reporting.

    Returns
    -------
    bool
        ``True`` on success, ``False`` if an exception occurred.
    """

    try:
        if forwards:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
        if backwards:
            bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
    except RuntimeError as exc:
        if logger:
            logger.error(f"track_markers failed: {exc}")
        else:
            print(f"track_markers failed: {exc}")
        return False

    return True

