"""Utility helpers for various clip operations."""


def get_active_clip(context):
    """Return the active clip from ``context``.

    The function first checks ``context.space_data`` for a clip and falls
    back to ``context.scene`` if necessary. ``None`` is returned when no
    clip is found.
    """
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None)
    if clip is None:
        scene = getattr(context, "scene", None)
        clip = getattr(scene, "clip", None)
    return clip
