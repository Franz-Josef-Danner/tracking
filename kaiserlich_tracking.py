bl_info = {
    "name": "Kaiserlich Tracking Operator",
    "author": "OpenAI",
    "version": (1, 0, 0),
    "blender": (4, 4, 3),
    "location": "Movie Clip Editor > Sidebar > Kaiserlich",
    "description": (
        "Automatisches Motion-Tracking mit adaptiver Marker-"
        "Platzierung und Kamera-Lösung"
    ),
    "category": "Movie Clip",
}

import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, IntProperty, PointerProperty


class KAISERLICHSettings(PropertyGroup):
    """Einstellungen für das Kaiserlich-Tracking."""

    markers_per_frame: IntProperty(
        name="Marker/Frame",
        description="Gewünschte Anzahl Marker pro Frame",
        default=10,
        min=1,
    )

    min_track_length: IntProperty(
        name="Frames/Track",
        description="Minimale Track-Länge in Frames",
        default=10,
        min=1,
    )

    error_threshold: FloatProperty(
        name="Error/Track",
        description="Tolerierter Fehler pro Track",
        default=1.0,
        min=0.0,
    )


class KAISERLICH_PT_Panel(Panel):
    """Panel für die Kaiserlich-Tracking Einstellungen."""

    bl_label = "Kaiserlich"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_context = "tracking"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        settings = wm.kaiserlich_settings

        layout.prop(settings, "markers_per_frame")
        layout.prop(settings, "min_track_length")
        layout.prop(settings, "error_threshold")
        layout.operator("clip.kaiserlich_tracking", text="Track")


class KAISERLICH_OT_Tracking(Operator):
    """Führt das Kaiserlich-Tracking aus."""

    bl_idname = "clip.kaiserlich_tracking"
    bl_label = "Run Kaiserlich Tracking"
    bl_description = (
        "Automatisches Feature-Tracking und Kamera-Lösung basierend "
        "auf den Kaiserlich-Parametern"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        wm = context.window_manager
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)

        if clip is None:
            self.report({"ERROR"}, "Kein aktiver Clip gefunden.")
            return {"CANCELLED"}

        markers_per_frame = wm.kaiserlich_settings.markers_per_frame
        min_frames = wm.kaiserlich_settings.min_track_length
        error_limit = wm.kaiserlich_settings.error_threshold

        tracking = clip.tracking
        settings = tracking.settings
        clip.use_proxy = False
        clip.proxy.build_25 = False
        clip.proxy.build_50 = False
        clip.proxy.build_75 = False
        clip.proxy.build_100 = False

        image_width = float(clip.size[0])
        settings.default_pattern_size = max(int(image_width / 100), 5)
        settings.default_search_size = settings.default_pattern_size
        settings.default_motion_model = "Loc"
        settings.default_pattern_match = "KEYFRAME"
        settings.default_correlation_min = 0.9

        bpy.ops.clip.select_all(action="DESELECT")
        margin = 16
        threshold = 0.5
        min_distance = int(image_width * 0.05)
        bpy.ops.clip.detect_features(
            placement="FRAME",
            margin=margin,
            threshold=threshold,
            min_distance=min_distance,
        )

        tracks = tracking.objects.active.tracks
        new_tracks = [t for t in tracks if t.select]
        count_new = len(new_tracks)
        if count_new < markers_per_frame:
            self.report(
                {"INFO"},
                f"Nur {count_new} neue Marker gefunden, weniger als Ziel {markers_per_frame}.",
            )

        if not new_tracks:
            self.report({"WARNING"}, "Keine Marker zum Tracken gefunden.")
            return {"CANCELLED"}

        for track in new_tracks:
            track.motion_model = "Loc"
            track.pattern_match = "KEYFRAME"
            track.use_red_channel = True
            track.use_green_channel = True
            track.use_blue_channel = True
            track.use_mask = False
            track.correlation_min = settings.default_correlation_min

        bpy.ops.clip.track_markers(backwards=False, sequence=True)
        bpy.ops.clip.track_markers(backwards=True, sequence=True)

        for track in list(tracks):
            if len(track.markers) < min_frames:
                track.select = True
            else:
                track.select = False
        if any(t.select for t in tracks):
            bpy.ops.clip.delete_track()

        bpy.ops.clip.clean_tracks(frames=0, error=error_limit, action="DELETE_TRACK")

        settings.keyframe_a = scene.frame_start
        settings.keyframe_b = scene.frame_end
        bpy.ops.clip.solve_camera()
        solve_error = tracking.objects.active.reconstruction_error
        self.report(
            {"INFO"},
            f"Kamera gelöst. Durchschnittlicher Solve-Fehler: {solve_error:.3f}",
        )

        bpy.ops.clip.set_scene_frames()
        bpy.ops.clip.setup_tracking_scene()

        for obj in scene.objects:
            if obj.type == "CAMERA" and obj.constraints:
                for constr in obj.constraints:
                    if constr.type == "CAMERA_SOLVER":
                        bpy.context.view_layer.objects.active = obj
                        bpy.ops.clip.constraint_to_fcurve()
                        constr.mute = True
                        break

        return {"FINISHED"}


def register():
    bpy.utils.register_class(KAISERLICHSettings)
    bpy.utils.register_class(KAISERLICH_OT_Tracking)
    bpy.utils.register_class(KAISERLICH_PT_Panel)
    bpy.types.WindowManager.kaiserlich_settings = PointerProperty(
        type=KAISERLICHSettings
    )


def unregister():
    del bpy.types.WindowManager.kaiserlich_settings
    bpy.utils.unregister_class(KAISERLICH_PT_Panel)
    bpy.utils.unregister_class(KAISERLICH_OT_Tracking)
    bpy.utils.unregister_class(KAISERLICHSettings)


if __name__ == "__main__":
    register()
