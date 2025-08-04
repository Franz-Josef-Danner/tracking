import bpy
from dataclasses import dataclass
from bpy.types import PropertyGroup
from bpy.props import BoolProperty, FloatProperty, IntProperty


@dataclass
class TrackingConfig:
    """Bündelt alle konfigurierbaren Tracking-Parameter."""

    markers_per_frame: int = 10
    min_frames: int = 10
    base_threshold: float = 0.5
    pattern_size: int = 21
    search_size: int = 96
    motion_model: str = "Loc"
    use_default_normalization: bool = True
    use_red: bool = True
    use_green: bool = False
    use_blue: bool = False
    use_default_mask: bool = False


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

    error_limit: FloatProperty(
        name="Error/Track",
        description="Tolerierter Fehler pro Track",
        default=1.0,
        min=0.0,
    )

    start_frame: IntProperty(
        name="Start Frame",
        default=1,
        min=1,
    )

    end_frame: IntProperty(
        name="End Frame",
        default=250,
        min=1,
    )

    enable_debug_overlay: BoolProperty(
        name="Debug Overlay",
        description="Markerabdeckung im UI anzeigen",
        default=False,
    )

    auto_keyframes: BoolProperty(
        name="Auto Keyframes",
        description="Keyframes A und B automatisch bestimmen",
        default=True,
    )

    bidirectional: BoolProperty(
        name="Bidirektional",
        description="Tracking vorwärts und rückwärts ausführen",
        default=True,
    )


__all__ = ["KaiserlichSettings", "TrackingConfig"]
