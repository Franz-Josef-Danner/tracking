"""Modal operator to rebuild 50% proxy and start tracking cycle."""

import bpy
import os


class KAISERLICH_OT_proxy_build_modal(bpy.types.Operator):
    """Rebuild proxy and trigger tracking once finished."""

    bl_idname = "kaiserlich.proxy_build_modal"
    bl_label = "Build Proxy and Track"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _proxy_paths = []
    _clip = None
    _checks = 0

    def execute(self, context):  # type: ignore[override]
        space = context.space_data
        clip = getattr(space, "clip", None)
        if not clip:
            self.report({'ERROR'}, "No clip loaded")
            return {'CANCELLED'}

        proxy = clip.proxy
        proxy_dir = bpy.path.abspath(proxy.directory)
        os.makedirs(proxy_dir, exist_ok=True)

        alt_dir = os.path.join(proxy_dir, os.path.basename(clip.filepath))
        for d in (proxy_dir, alt_dir):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.startswith("proxy_"):
                        try:
                            os.remove(os.path.join(d, f))
                        except OSError:
                            pass

        print("[Proxy] building 50% proxy...")

        override = context.copy()
        override['area'] = next(a for a in context.screen.areas if a.type == 'CLIP_EDITOR')
        override['region'] = next(r for r in override['area'].regions if r.type == 'WINDOW')
        override['space_data'] = override['area'].spaces.active
        override['clip'] = clip

        with context.temp_override(**override):
            bpy.ops.clip.rebuild_proxy()

        proxy_file = "proxy_50.avi"
        direct_path = os.path.join(proxy_dir, proxy_file)
        alt_path = os.path.join(proxy_dir, os.path.basename(clip.filepath), proxy_file)

        self._clip = clip
        self._proxy_paths = [direct_path, alt_path]
        self._checks = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        self.report({'INFO'}, "Proxy 50% Erstellung gestartet")
        print("[Proxy] build started")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):  # type: ignore[override]
        if event.type == 'TIMER':
            if any(os.path.exists(p) for p in self._proxy_paths):
                context.window_manager.event_timer_remove(self._timer)
                context.scene.proxy_built = True
                self.report({'INFO'}, "\u2705 Proxy-Erstellung abgeschlossen")
                print("[Proxy] build finished")

                bpy.ops.clip.tracking_cycle('INVOKE_DEFAULT')
                return {'FINISHED'}
            self._checks += 1
        return {'PASS_THROUGH'}

    def cancel(self, context):  # type: ignore[override]
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}


__all__ = ["KAISERLICH_OT_proxy_build_modal"]
