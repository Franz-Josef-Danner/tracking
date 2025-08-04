import bpy
from bpy.types import PropertyGroup
from bpy.props import BoolProperty, FloatProperty, IntProperty


class KaiserlichSettings(PropertyGroup):
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

    auto_keyframes: BoolProperty(
        name="Auto Keyframes",
        description="Keyframes A und B automatisch bestimmen",
        default=True,
    )


__all__ = ["KaiserlichSettings"]
