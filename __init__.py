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
    _BPy = True
except ModuleNotFoundError:  # Allow running tests without Blender
    import types
    bpy = types.SimpleNamespace()
    Panel = Operator = AddonPreferences = object
    IntProperty = FloatProperty = BoolProperty = lambda *a, **k: None
    _BPy = False
import os
import sys
import importlib
import logging

# pattern size handling
PATTERN_SIZE_START = 50
PATTERN_SIZE_MAX = 100

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


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
        "playhead",
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


if _BPy:
    from few_marker_frame import (
        find_frame_with_few_tracking_markers,
    )
    from marker_count_plus import update_marker_count_plus
    from margin_utils import compute_margin_distance
    from playhead import (
        get_tracking_marker_counts,
        set_playhead_to_low_marker_frame,
    )
    from count_new_markers import check_marker_range, count_new_markers
    import proxy_wait
    importlib.reload(proxy_wait)
    from proxy_wait import create_proxy_and_wait, remove_existing_proxies
    from update_min_marker_props import update_min_marker_props
    from distance_remove import CLIP_OT_remove_close_new_markers
    from proxy_switch import ToggleProxyOperator
    from detect import DetectFeaturesCustomOperator
    from iterative_detect import detect_until_count_matches
    from track_cycle import auto_track_bidirectional
    from delete_helpers import delete_short_tracks
    from rename_new import rename_tracks
    from New.motion_model import cycle_motion_model, reset_motion_model

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


visited_frames = set()


def run_tracking_cycle(context, clip, min_marker, min_track_len):
    """Iteratively detect and track until all frames meet ``min_marker``.

    The global ``visited_frames`` set stores each processed frame so it is not
    removed between operator executions.
    """

    scene = context.scene
    settings = clip.tracking.settings
    global visited_frames
    visited_frames.clear()
    pattern_size = min(PATTERN_SIZE_START, PATTERN_SIZE_MAX)
    settings.default_pattern_size = pattern_size
    start = scene.frame_start
    end = scene.frame_end
    total = end - start + 1
    if _BPy:
        context.window_manager.progress_begin(0, total)
    scene.tracking_progress = 0.0

    while True:
        counts = get_tracking_marker_counts()
        frame = find_frame_with_few_tracking_markers(counts, min_marker)
        if frame is None:
            break

        progress = (frame - start) / total
        scene.tracking_progress = max(0.0, min(1.0, progress))
        if _BPy:
            context.window_manager.progress_update(frame - start)

        scene.frame_current = frame
        logger.info(f"Playhead auf Frame {frame} gesetzt.")

        if frame not in visited_frames:
            visited_frames.add(frame)
            reset_motion_model(settings)
            pattern_size = max(1, int(pattern_size * 0.9))
            pattern_size = min(pattern_size, PATTERN_SIZE_MAX)
        else:
            cycle_motion_model(settings)
            pattern_size = int(pattern_size * 1.1)
            pattern_size = min(pattern_size, PATTERN_SIZE_MAX)

        settings.default_pattern_size = pattern_size
        settings.default_search_size = settings.default_pattern_size * 2
        logger.info(
            "Tracking: pattern_size=%s motion_model=%s",
            pattern_size,
            settings.default_motion_model,
        )

        compute_margin_distance()
        update_marker_count_plus(scene)

        new_count = detect_until_count_matches(context)
        scene.new_marker_count = new_count

        auto_track_bidirectional(context)

        deleted = delete_short_tracks(context, min_track_len, prefix="TRACK_")
        if deleted:
            logger.info(f"🗑️ Gelöscht: {deleted} kurze TRACK_ Marker")
            show_popup(f"Gelöscht: {deleted} kurze TRACK_ Marker")

        remaining = [
            t for t in clip.tracking.tracks if t.name.startswith("TRACK_")
        ]
        if remaining:
            rename_tracks(remaining, prefix="GOOD_")
            logger.info(
                f"✅ Umbenannt: {len(remaining)} TRACK_ Marker zu GOOD_"
            )

    if _BPy:
        context.window_manager.progress_update(total)
        context.window_manager.progress_end()
    scene.tracking_progress = 1.0
    logger.info("Keine Frames mit zu wenigen Markern mehr gefunden")




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
            if clip:
                if not clip.use_proxy:
                    logger.info("Proxy-Zeitlinie wird aktiviert")
                    clip.use_proxy = True
                    show_popup("Proxy-Zeitlinie wurde aktiviert")
                else:
                    logger.info("Proxy bereits aktiviert")
                    show_popup("Proxy bereits aktiviert")
            else:
                logger.info("Kein Clip für Proxy-Schaltung")
                show_popup("Kein Clip für Proxy-Schaltung")

            logger.info("Berechne minimale Marker-Eigenschaften")
            update_min_marker_props(scene, context)
            marker_counts = get_tracking_marker_counts()
            frame = find_frame_with_few_tracking_markers(marker_counts, min_marker)
            if frame is not None:
                context.scene.frame_current = frame
                logger.info(f"Playhead auf Frame {frame} gesetzt.")


            def run_ops():
                # Proxy einschalten, falls noch deaktiviert
                if clip and not clip.use_proxy:
                    bpy.ops.clip.toggle_proxy()

                scene.tracking_progress = 0.0

                run_tracking_cycle(bpy.context, clip, min_marker, min_track_len)

                # Nach Abschluss sicherstellen, dass kein Frame mehr uebrig ist
                set_playhead_to_low_marker_frame(min_marker)

            if not run_in_clip_editor(clip, run_ops):
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
        layout.prop(scene, "tracking_progress", slider=True)
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
    bpy.types.Scene.tracking_progress = FloatProperty(
        name="Tracking Progress",
        subtype='PERCENTAGE',
        default=0.0,
        min=0.0,
        max=1.0,
    )
    bpy.utils.register_class(ToggleProxyOperator)
    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(KaiserlichAddonPreferences)
    bpy.utils.register_class(CLIP_OT_kaiserlich_track)
    bpy.utils.register_class(CLIP_PT_kaiserlich_track)
    bpy.utils.register_class(CLIP_OT_remove_close_new_markers)
    configure_logging()


def unregister():
    bpy.utils.unregister_class(CLIP_OT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.unregister_class(ToggleProxyOperator)
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    bpy.utils.unregister_class(KaiserlichAddonPreferences)
    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_tracking_length
    del bpy.types.Scene.error_threshold
    del bpy.types.Scene.min_marker_count_plus
    del bpy.types.Scene.marker_count_plus_min
    del bpy.types.Scene.marker_count_plus_max
    del bpy.types.Scene.new_marker_count
    del bpy.types.Scene.tracking_progress


if __name__ == "__main__":
    register()
