# SPDX-License-Identifier: GPL-2.0-or-later
"""Repeat-Scope Overlay: einfacher Draw-Handler mit Register-Hooks."""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_HANDLE = None
_REGISTERED = False


def register() -> None:
    global _REGISTERED
    _REGISTERED = True
    print("[Scope] register()")
    try:
        from ..Helper.properties import is_repeat_scope_enabled

        scn = bpy.context.scene
        if is_repeat_scope_enabled(scn):
            ensure_repeat_scope_handler(scn)
            print("[Scope] auto-ensure handler on register (enabled=True)")
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] auto-ensure on register failed: {e!r}")


def unregister() -> None:
    global _REGISTERED
    _REGISTERED = False
    print("[Scope] unregister()")
    try:
        disable_repeat_scope_handler()
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler remove on unregister failed: {e!r}")


def _get_series():
    scn = bpy.context.scene
    return scn.get("_kc_repeat_series") or []


def _draw_repeat_scope():
    series = _get_series()
    if not series:
        return
    try:
        shader = gpu.shader.from_builtin("2D_UNIFORM_COLOR")
        batch = batch_for_shader(shader, "POINTS", {"pos": [(0, 0)]})
        shader.bind()
        shader.uniform_float("color", (1, 1, 1, 1))
        batch.draw(shader)
    except Exception:  # noqa: BLE001
        pass


def ensure_repeat_scope_handler(_scene=None):
    global _HANDLE
    if _HANDLE is not None:
        return
    try:
        _HANDLE = bpy.types.SpaceClipEditor.draw_handler_add(
            _draw_repeat_scope, (), "WINDOW", "POST_PIXEL"
        )
        print("[Scope] handler added")
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler add failed: {e!r}")


def disable_repeat_scope_handler():
    global _HANDLE
    if _HANDLE is None:
        return
    try:
        bpy.types.SpaceClipEditor.draw_handler_remove(_HANDLE, "WINDOW")
        print("[Scope] handler removed")
    except Exception as e:  # noqa: BLE001
        print(f"[Scope][WARN] handler remove failed: {e!r}")
    _HANDLE = None

