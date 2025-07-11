bl_info = {
    "name": "Kaiserlich Track",
    "author": "OpenAI Assistant",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich Track",
    "description": "Panel for custom Kaiserlich tracking options",
    "category": "Movie Clip",
}

import bpy
from bpy.types import Panel, Operator
from bpy.props import IntProperty, FloatProperty
import os
import sys
import importlib

# Ensure helper modules in this directory can be imported when the addon is
# installed as a single-file module. Blender does not automatically add the
# addon folder to ``sys.path`` when ``__init__.py`` sits at the root of the
# archive, so do it manually before other imports.
addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

import marker_count_property

from find_frame_with_few_tracking_markers import (
    find_frame_with_few_tracking_markers,
)
from get_marker_count_plus import get_marker_count_plus
from margin_a_distanz import compute_margin_distance
from playhead import (
    set_playhead_to_low_marker_frame,
    get_tracking_marker_counts,
)
import proxy_wait
importlib.reload(proxy_wait)
from proxy_wait import create_proxy_and_wait, remove_existing_proxies
from update_min_marker_props import update_min_marker_props
from distance_remove import CLIP_OT_remove_close_new_markers
from proxy_switch import ToggleProxyOperator
from detect import DetectFeaturesCustomOperator




class CLIP_OT_kaiserlich_track(Operator):
    bl_idname = "clip.kaiserlich_track_start"
    bl_label = "Start Kaiserlich Track"
    bl_description = "Start the Kaiserlich tracking operation"

    def execute(self, context):
        scene = context.scene
        min_marker = scene.kt_min_marker_per_frame
        min_track_len = scene.kt_min_tracking_length
        error_threshold = scene.kt_error_threshold
        # Wartezeit für die Proxy-Erstellung (in Sekunden)
        wait_time = 300.0

        update_min_marker_props(scene, context)
        marker_counts = get_tracking_marker_counts()
        frame = find_frame_with_few_tracking_markers(marker_counts, min_marker)
        if frame is not None:
            set_playhead_to_low_marker_frame(min_marker)

        compute_margin_distance()
        marker_plus = get_marker_count_plus(scene)
        self.report(
            {'INFO'},
            (
                f"Start with min markers {min_marker}, length {min_track_len}, "
                f"error {error_threshold}, derived {marker_plus}"
            ),
        )
        # Alte Proxies entfernen
        remove_existing_proxies()
        # 50% Proxy erstellen und etwas warten. Manche
        # Installationen liefern eine Version ohne Parameter.
        try:
            print("✅ Aufruf: create_proxy_and_wait() wird gestartet")
            create_proxy_and_wait(wait_time)
        except TypeError:
            # Fallback für ältere Skripte ohne Argument
            create_proxy_and_wait()

        # Proxy-Zeitlinie wieder deaktivieren
        clip = context.space_data.clip
        if clip and clip.use_proxy:
            print("Proxy-Zeitlinie wird deaktiviert")
            bpy.ops.clip.toggle_proxy()
        else:
            print("Proxy bereits deaktiviert oder kein Clip")

        # Property registration for marker counts
        marker_count_property.register()

        # Marker erkennen und bereinigen
        print("Starte Feature-Erkennung")
        bpy.ops.clip.detect_features_custom()
        print("Bereinige Marker")
        bpy.ops.clip.remove_close_new_markers()

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
        layout.prop(scene, "kt_min_marker_per_frame")
        layout.prop(scene, "kt_min_tracking_length")
        layout.prop(scene, "kt_error_threshold")
        layout.operator(CLIP_OT_kaiserlich_track.bl_idname, text="Start")


def register():
    bpy.types.Scene.kt_min_marker_per_frame = IntProperty(
        name="min marker pro frame",
        default=10,
        min=0,
    )
    bpy.types.Scene.kt_min_tracking_length = IntProperty(
        name="min tracking length",
        default=20,
        min=0,
    )
    bpy.types.Scene.kt_error_threshold = FloatProperty(
        name="Error Threshold",
        default=0.04,
        min=0.0,
    )
    bpy.types.Scene.min_marker_count = IntProperty(
        name="Min Marker Count",
        default=5,
        min=5,
        max=50,
        update=update_min_marker_props,
    )
    bpy.types.Scene.min_marker_count_plus = IntProperty(
        name="Marker Count Plus",
        default=20,
        min=0,
    )
    bpy.utils.register_class(ToggleProxyOperator)
    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(CLIP_OT_kaiserlich_track)
    bpy.utils.register_class(CLIP_PT_kaiserlich_track)
    bpy.utils.register_class(CLIP_OT_remove_close_new_markers)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_PT_kaiserlich_track)
    bpy.utils.unregister_class(CLIP_OT_remove_close_new_markers)
    bpy.utils.unregister_class(ToggleProxyOperator)
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    del bpy.types.Scene.kt_min_marker_per_frame
    del bpy.types.Scene.kt_min_tracking_length
    del bpy.types.Scene.kt_error_threshold
    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_marker_count_plus


if __name__ == "__main__":
    register()
