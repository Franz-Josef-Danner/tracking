"""Modal operator for asynchronous track renaming."""

from __future__ import annotations

import bpy

try:
    from bpy.types import Event as BpyEvent
    VALID_EVENT_TYPES = {
        item.identifier for item in BpyEvent.bl_rna.properties["type"].enum_items
    }
except Exception:  # pragma: no cover - gracefully handle missing bpy in tests
    BpyEvent = None
    VALID_EVENT_TYPES = set()

from ..util.tracker_logger import TrackerLogger


class KAISERLICH_OT_rename_tracks_modal(bpy.types.Operator):
    """Rename tracking tracks asynchronously."""

    bl_idname = "kaiserlich.rename_tracks_modal"
    bl_label = "Rename Tracks"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _tracks = []
    _index = 0
    _logger = None

    def execute(self, context):
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        self._tracks = list(clip.tracking.tracks)
        self._index = 0
        self._logger = TrackerLogger()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        event_type = getattr(event, "type", None)
        if not isinstance(event_type, str):
            return {'PASS_THROUGH'}
        if event_type not in VALID_EVENT_TYPES:
            return {'PASS_THROUGH'}

        if event_type == 'TIMER':
            if self._index >= len(self._tracks):
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            track = self._tracks[self._index]
            if not track.name.startswith("TRACK_"):
                new_name = f"TRACK_{track.name}"
                try:
                    track.name = new_name
                except RuntimeError as exc:
                    if self._logger:
                        self._logger.warn(f"Failed to rename track {track.name} -> {new_name}: {exc}")
            self._index += 1
        return {'PASS_THROUGH'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}


__all__ = ["KAISERLICH_OT_rename_tracks_modal"]
