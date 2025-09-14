# SPDX-License-Identifier: GPL-2.0-or-later
# UI Bootstrap – nur noch Repeat-Scope aktiv, Legacy wird proaktiv entfernt.
import sys


def _purge_legacy_overlay_modules() -> None:
    names = [
        f"{__package__}.overlay",
        f"{__package__}.overlay_impl",
        f"{__package__}.legacy_overlay",
    ]
    for name in names:
        mod = sys.modules.get(name)
        if not mod:
            continue
        for attr in ("disable_overlay_handler", "disable_handler", "unregister", "remove_handler"):
            fn = getattr(mod, attr, None)
            if callable(fn):
                try:
                    fn()
                    print(f"[LegacyOverlay] {name}.{attr}() → OK")
                except Exception as e:
                    print(f"[LegacyOverlay][WARN] {name}.{attr}() failed: {e!r}")
        sys.modules.pop(name, None)
        print(f"[LegacyOverlay] purged module: {name}")


def register() -> None:
    from . import repeat_scope as _rs

    _purge_legacy_overlay_modules()
    try:
        if hasattr(_rs, "register"):
            _rs.register()
            print("[UI] repeat_scope.register OK")
        else:
            try:
                import bpy
                from ..Helper.properties import is_repeat_scope_enabled

                scn = bpy.context.scene
                if is_repeat_scope_enabled(scn) and hasattr(_rs, "ensure_repeat_scope_handler"):
                    _rs.ensure_repeat_scope_handler(scn)
                    print("[UI] repeat_scope.ensure handler (fallback) OK")
            except Exception as e:  # noqa: BLE001
                print(f"[UI][WARN] repeat_scope fallback ensure failed: {e!r}")
    except Exception as e:  # noqa: BLE001
        print(f"[UI][WARN] repeat_scope.register failed: {e!r}")
    print("[UI] registered – legacy overlay removed")


def unregister() -> None:
    from . import repeat_scope as _rs

    try:
        if hasattr(_rs, "unregister"):
            _rs.unregister()
        elif hasattr(_rs, "disable_repeat_scope_handler"):
            _rs.disable_repeat_scope_handler()
    except Exception as e:  # noqa: BLE001
        print(f"[UI][WARN] repeat_scope.unregister failed: {e!r}")
    _purge_legacy_overlay_modules()
    print("[UI] unregistered – legacy overlay removed")

