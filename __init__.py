BLENDER_AVAILABLE = False
bl_info = {
    "name": "Kaiserlich Track",
    "author": "OpenAI Assistant",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich Track",
    "description": "Panel for custom Kaiserlich tracking options",
    "category": "Movie Clip",
}

try:
    import bpy
    from bpy.types import Panel, Operator, AddonPreferences
    from bpy.props import IntProperty, FloatProperty, BoolProperty
    BLENDER_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - not running inside Blender
    import types
    import sys

    bpy = types.SimpleNamespace()
    sys.modules['bpy'] = bpy

    class Panel:
        pass

    class Operator:
        pass

    class AddonPreferences:
        pass

    def IntProperty(**_kwargs):
        return None

    def FloatProperty(**_kwargs):
        return None

    def BoolProperty(**_kwargs):
        return None
import os
import sys
import importlib
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Optional callback invoked after feature detection has finished
after_detect_callback = None

def register_after_detect_callback(func):
    """Register ``func`` to run after feature detection completes."""
    global after_detect_callback
    after_detect_callback = func


def configure_logging():
    """Set log level based on addon preferences."""
    addon = bpy.context.preferences.addons.get(__name__)
    enable = addon and getattr(addon.preferences, "enable_detailed_logs", False)
    level = logging.INFO if enable else logging.WARNING
    logger.setLevel(level)
    for name in (
        __name__,
        "count_new_markers",
        "detect",
        "iterative_detect",
        "margin_utils",
        "proxy_wait",
    ):
        logging.getLogger(name).setLevel(level)


class KaiserlichAddonPreferences(AddonPreferences):
    bl_idname = __name__

    enable_detailed_logs: BoolProperty(
        name="Enable detailed logs",
        description="Output additional info to the console",
        default=False,
        update=lambda self, context: configure_logging(),
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "enable_detailed_logs")

# Ensure helper modules in this directory can be imported when the addon is
# installed as a single-file module. Blender does not automatically add the
# addon folder to ``sys.path`` when ``__init__.py`` sits at the root of the
# archive, so do it manually before other imports.
addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

if BLENDER_AVAILABLE:
    from few_marker_frame import (
        set_playhead_to_low_marker_frame,
    )
    from marker_count_plus import update_marker_count_plus
    from adjust_marker_count_plus import (
        increase_marker_count_plus,
        decrease_marker_count_plus,
    )
    from motion_model import cycle_motion_model, reset_motion_model
    from margin_utils import compute_margin_distance

    from count_new_markers import check_marker_range, count_new_markers
    import proxy_wait
    importlib.reload(proxy_wait)
    from proxy_wait import create_proxy_and_wait, remove_existing_proxies
    from update_min_marker_props import update_min_marker_props
    from distance_remove import CLIP_OT_remove_close_new_markers
    from proxy_switch import ToggleProxyOperator
    from detect import DetectFeaturesCustomOperator
    from iterative_detect import detect_until_count_matches
    from auto_track_bidir import TRACK_OT_auto_track_bidir

def show_popup(message, title="Info", icon='INFO'):
    """Display a temporary popup in Blender's UI."""

    def draw(self, _context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def run_in_clip_editor(clip, func):
    """Execute ``func`` with a Clip Editor override and set its clip."""
    ctx = bpy.context
    for area in ctx.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    for space in area.spaces:
                        if space.type == 'CLIP_EDITOR':
                            space.clip = clip
                            with ctx.temp_override(area=area, region=region, space_data=space):
                                func()
                            return True
    return False




class CLIP_OT_kaiserlich_track(Operator):
    bl_idname = "clip.kaiserlich_track_start"
    bl_label = "Start Kaiserlich Track"
    bl_description = "Start the Kaiserlich tracking operation"

    def execute(self, context):
        scene = context.scene
        min_marker = scene.min_marker_count
        min_track_len = scene.min_tracking_length
        error_threshold = scene.error_threshold
        # Wartezeit für die Proxy-Erstellung (in Sekunden)
        wait_time = 300.0

        # Schritte nach Abschluss des Proxy-Aufbaus.
        # Der aktuelle Clip wird übergeben, damit der Callback unabhängig vom
        # aktiven Kontext funktioniert.
        def after_proxy(clip):
            if clip and clip.use_proxy:
                logger.info("Proxy-Zeitlinie wird deaktiviert")
                clip.use_proxy = False
                show_popup("Proxy-Zeitlinie wurde deaktiviert")
            else:
                logger.info("Proxy bereits deaktiviert oder kein Clip")
                show_popup("Proxy bereits deaktiviert oder kein Clip")

            logger.info("Berechne minimale Marker-Eigenschaften")
            update_min_marker_props(scene, context)
            scene.repeat_frame_hits = 0


            def run_ops(on_after_detect=None):
                compute_margin_distance()
                marker_plus = update_marker_count_plus(scene)
                msg = (
                    f"Start with min markers {min_marker}, length {min_track_len}, "
                    f"error {error_threshold}, derived {marker_plus}"
                )
                logger.info(msg)
                logger.info("Starte Feature-Erkennung")
                sys.stdout.flush()

                new_count = detect_until_count_matches(context)
                scene.new_marker_count = new_count
                logger.info(f"TRACK_ Marker nach Iteration: {new_count}")

                frame = set_playhead_to_low_marker_frame(min_marker)
                if frame is not None:
                    space = context.space_data
                    clip_local = getattr(space, "clip", None)
                    if clip_local:
                        settings = clip_local.tracking.settings
                        if scene.repeat_frame == frame:
                            scene.repeat_frame_hits += 1
                            if scene.repeat_frame_hits >= 10:
                                logger.warning(
                                    "Frame %s wurde 10 mal gefunden, breche ab",
                                    frame,
                                )
                                show_popup(
                                    f"Tracking abgebrochen: Frame {frame} 10 mal gefunden",
                                    icon='ERROR',
                                )
                                return
                            cycle_motion_model(settings)
                            increase_marker_count_plus(scene)
                        else:
                            scene.repeat_frame = frame
                            scene.repeat_frame_hits = 1
                            reset_motion_model(settings)
                            decrease_marker_count_plus(scene, scene.marker_count_plus_base)
                        new_count = detect_until_count_matches(context)
                        scene.new_marker_count = new_count
                        logger.info(f"TRACK_ Marker nach Iteration: {new_count}")

                if on_after_detect:
                    try:
                        on_after_detect(context)
                    except Exception:
                        logger.exception("Fehler im After-Detect Callback")

            if not run_in_clip_editor(clip, lambda: run_ops(after_detect_callback)):
                logger.info("Kein Clip Editor zum Ausführen der Operatoren gefunden")

        # Alte Proxies entfernen
        active_clip = context.space_data.clip
        remove_existing_proxies(active_clip)
        # 50% Proxy erstellen und warten, bis Dateien erscheinen
        logger.info("✅ Aufruf: create_proxy_and_wait() wird gestartet")
        create_proxy_and_wait(wait_time, on_finish=after_proxy, clip=active_clip)

        return {'FINISHED'}


class CLIP_PT_kaiserlich_track(Panel):
    bl_label = "Kaiserlich Track"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kaiserlich"
    bl_context = "tracking"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "min_marker_count")
        layout.prop(scene, "min_tracking_length")
        layout.prop(scene, "error_threshold")
        layout.operator(CLIP_OT_kaiserlich_track.bl_idname, text="Start")


def register():
    bpy.types.Scene.min_marker_count = IntProperty(
        name="min marker pro frame",
        default=10,
        min=0,
        update=update_min_marker_props,
    )
    bpy.types.Scene.min_tracking_length = IntProperty(
        name="min tracking length",
        default=20,
        min=0,
    )
    bpy.types.Scene.error_threshold = FloatProperty(
        name="Error Threshold",
        default=0.04,
        min=0.0,
    )
    bpy.types.Scene.min_marker_count_plus = IntProperty(
        name="Marker Count Plus",
        default=20,
        min=0,
    )
    bpy.types.Scene.marker_count_plus_min = IntProperty(
        name="Marker Count Plus Min",
        default=0,
        min=0,
    )
    bpy.types.Scene.marker_count_plus_max = IntProperty(
        name="Marker Count Plus Max",
        default=0,
        min=0,
    )
    bpy.types.Scene.new_marker_count = IntProperty(
        name="NEW_ Marker Count",
        default=0,
        min=0,
    )
    bpy.types.Scene.marker_count_plus_base = IntProperty(
        name="Marker Count Plus Base",
        default=0,
        min=0,
    )
    bpy.types.Scene.repeat_frame = IntProperty(
        name="Repeat Frame",
        default=-1,
        min=-1,
    )
    bpy.types.Scene.repeat_frame_hits = IntProperty(
        name="Repeat Frame Hits",
        default=0,
        min=0,
    )
    bpy.utils.register_class(ToggleProxyOperator)
    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(KaiserlichAddonPreferences)
    bpy.utils.register_class(CLIP_OT_kaiserlich_track)
    bpy.utils.register_class(CLIP_PT_kaiserlich_track)
    bpy.utils.register_class(TRACK_OT_auto_track_bidir)
    bpy.utils.register_class(CLIP_OT_remove_close_new_markers)
    configure_logging()


def unregister():
    bpy.utils.unregister_class(CLIP_OT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.unregister_class(ToggleProxyOperator)
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    bpy.utils.unregister_class(KaiserlichAddonPreferences)
    bpy.utils.unregister_class(TRACK_OT_auto_track_bidir)
    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_tracking_length
    del bpy.types.Scene.error_threshold
    del bpy.types.Scene.min_marker_count_plus
    del bpy.types.Scene.marker_count_plus_min
    del bpy.types.Scene.marker_count_plus_max
    del bpy.types.Scene.new_marker_count
    del bpy.types.Scene.marker_count_plus_base
    del bpy.types.Scene.repeat_frame
    del bpy.types.Scene.repeat_frame_hits


if __name__ == "__main__":
    register()
