"""Operator to run multiple actions without the proxy step."""

from __future__ import annotations

import bpy


class KAISERLICH_OT_run_all_except_proxy(bpy.types.Operator):  # type: ignore[misc]
    """Execute all Kaiserlich actions except the proxy builder."""

    bl_idname = "kaiserlich.run_all_except_proxy"
    bl_label = "Run All Except Proxy"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):  # type: ignore[override]
        bpy.ops.kaiserlich.detect_features()
        bpy.ops.kaiserlich.tracking_marker()
        bpy.ops.kaiserlich.cleanup_new_tracks()
        return {'FINISHED'}


__all__ = ["KAISERLICH_OT_run_all_except_proxy"]
