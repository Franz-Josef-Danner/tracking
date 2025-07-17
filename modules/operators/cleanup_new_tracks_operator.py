"""Operator to remove all NEW_ tracks from the active clip."""

from __future__ import annotations

import bpy

from ..util.tracking_utils import hard_remove_new_tracks
from ..util.tracker_logger import TrackerLogger, configure_logger


class KAISERLICH_OT_cleanup_new_tracks(bpy.types.Operator):  # type: ignore[misc]
    """Remove all tracks with the NEW_ prefix."""

    bl_idname = "kaiserlich.cleanup_new_tracks"
    bl_label = "Cleanup NEW Tracks"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):  # type: ignore[override]
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        configure_logger(debug=getattr(context.scene, "debug_output", False))
        logger = TrackerLogger()

        failed = hard_remove_new_tracks(clip, logger=logger)
        if failed:
            self.report({'WARNING'}, f"Could not remove {len(failed)} tracks")
        return {'FINISHED'}


__all__ = ["KAISERLICH_OT_cleanup_new_tracks"]
