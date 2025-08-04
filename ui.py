import bpy
import json
from bpy.types import Operator, Panel
from bpy.props import PointerProperty
from .settings import KaiserlichSettings
from .track import run_tracking
from .cleanup import compute_error_value


class KaiserlichPanel(Panel):
    """Panel für die Kaiserlich-Tracking Einstellungen."""

    bl_label = "Kaiserlich"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "UI"
    bl_category = "Kaiserlich"
    bl_context = "tracking"

    def draw(self, context):
        print("Drawing Kaiserlich panel")
        layout = self.layout
        settings = context.window_manager.kaiserlich_settings
        layout.prop(settings, "markers_per_frame")
        layout.prop(settings, "min_track_length")
        layout.prop(settings, "error_limit")
        layout.prop(settings, "start_frame")
        layout.prop(settings, "end_frame")
        layout.prop(settings, "auto_keyframes")
        layout.prop(settings, "bidirectional")
        layout.prop(settings, "enable_debug_overlay")
        layout.operator("clip.kaiserlich_tracking", text="Track")
        error_std = context.scene.get("kaiserlich_error_std")
        if error_std is not None:
            layout.label(
                text=f"Fehlerwert (STD-Summe): {error_std:.4f}"
            )
        layout.separator()
        layout.label(text="Diagnose")
        layout.operator("clip.error_value", text="Error Value")

        if settings.enable_debug_overlay:
            counts_raw = getattr(context.scene, "kaiserlich_marker_counts", "")
            try:
                counts = json.loads(counts_raw) if counts_raw else {}
            except Exception:
                counts = {}
            frame = context.scene.frame_current
            layout.label(
                text=f"Frame {frame}: {counts.get(str(frame), 0)} marker"
            )
            layout.label(
                text=f"Letzter Threshold: {context.scene.get('kaiserlich_last_threshold', '-') }"
            )
            clip = getattr(context.space_data, "clip", None)
            if clip is not None:
                layout.label(text=f"Gesamtmarker: {len(clip.tracking.tracks)}")


class KaiserlichTrackingOperator(Operator):
    """Führt das Kaiserlich-Tracking aus."""

    bl_idname = "clip.kaiserlich_tracking"
    bl_label = "Run Kaiserlich Tracking"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        print("Executing KaiserlichTrackingOperator")
        wm = context.window_manager
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"ERROR"}, "Kein aktiver Clip gefunden.")
            return {"CANCELLED"}
        tracking = clip.tracking
        key_a = wm.kaiserlich_settings.start_frame
        key_b = wm.kaiserlich_settings.end_frame
        markers = wm.kaiserlich_settings.markers_per_frame
        min_frames = wm.kaiserlich_settings.min_track_length
        print(
            f"Starting run_tracking with markers={markers}, min_frames={min_frames}"
        )
        bidirectional = wm.kaiserlich_settings.bidirectional
        run_tracking(
            context,
            markers,
            min_frames,
            bidirectional=bidirectional,
            report_func=self.report,
        )

        tracking_obj = tracking.objects.active
        valid_tracks = [
            t for t in tracking_obj.tracks if len([m for m in t.markers if not m.mute]) >= 5
        ]
        if len(valid_tracks) < 8:
            print("Not enough valid tracks for camera solving")
            self.report(
                {"ERROR"}, "Zu wenige gültige Tracks für Kameralösung (mind. 8 benötigt)",
            )
            return {"CANCELLED"}

        if wm.kaiserlich_settings.auto_keyframes:
            print("Setting keyframes automatically")
            bpy.ops.clip.set_keyframe_a()
            bpy.ops.clip.set_keyframe_b()

        try:
            print("Solving camera")
            bpy.ops.clip.solve_camera()
        except RuntimeError as e:
            self.report({"ERROR"}, f"Lösung fehlgeschlagen: {str(e)}")
            return {"CANCELLED"}

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

        print("KaiserlichTrackingOperator finished")
        return {"FINISHED"}


class ClipErrorValueOperator(Operator):
    """Berechnet die durchschnittliche Standardabweichung der Marker-Positionen."""

    bl_idname = "clip.error_value"
    bl_label = "Compute Error Value"
    bl_options = {"REGISTER"}

    def execute(self, context):
        print("Executing ClipErrorValueOperator")
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({"ERROR"}, "Kein aktiver Clip gefunden.")
            return {"CANCELLED"}
        tracking_obj = clip.tracking.objects.active
        if tracking_obj is None:
            self.report({"ERROR"}, "Kein aktives Tracking-Objekt vorhanden.")
            return {"CANCELLED"}
        avg_std = compute_error_value(tracking_obj)
        print(f"Computed average std dev: {avg_std}")
        if avg_std is None:
            self.report({"INFO"}, "Keine gültigen Tracks zur Berechnung.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Durchschnittliche Std-Abweichung: {avg_std:.4f}")
        return {"FINISHED"}


classes = [
    KaiserlichSettings,
    KaiserlichPanel,
    KaiserlichTrackingOperator,
    ClipErrorValueOperator,
]


def register():
    print("Registering Kaiserlich UI classes")
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kaiserlich_settings = PointerProperty(
        type=KaiserlichSettings
    )


def unregister():
    print("Unregistering Kaiserlich UI classes")
    del bpy.types.WindowManager.kaiserlich_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    "register",
    "unregister",
    "KaiserlichTrackingOperator",
    "KaiserlichPanel",
    "ClipErrorValueOperator",
]
