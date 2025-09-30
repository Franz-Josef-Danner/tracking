import bpy

class TRACKING_PG_detect_settings(bpy.types.PropertyGroup):
    min_distance_px: bpy.props.FloatProperty(
        name="Min Dist (px)",
        description="Mindestabstand zwischen Markern – neue zu nahe Marker werden gelöscht",
        default=6.0,
        min=0.1,
        max=200.0,
        precision=2
    )
    use_overlap: bpy.props.BoolProperty(
        name="BBox Overlap",
        description="Pattern-Bounding-Box Überlappung zusätzlich für Duplikaterkennung verwenden",
        default=True
    )
    overlap_threshold: bpy.props.FloatProperty(
        name="Overlap Schwelle",
        description="Relative Überlappung (gegen kleinere Fläche) ab der gelöscht wird",
        default=0.2,
        min=0.01,
        max=1.0,
        precision=3
    )
    rounding_step: bpy.props.FloatProperty(
        name="Rundung (px)",
        description="Rundet Marker-Zentren vor Distanzvergleich (0 = aus)",
        default=0.25,
        min=0.0,
        max=10.0,
        precision=3
    )
    tag_pass_names: bpy.props.BoolProperty(
        name="Pass-Präfixe",
        description="Neue Tracks erhalten ein 'P#_' Präfix zur Analyse je Durchlauf",
        default=True
    )
    debug: bpy.props.BoolProperty(
        name="Debug Log",
        description="Ausführliche Log-Ausgaben in der Konsole",
        default=False
    )
    cluster_cleanup: bpy.props.BoolProperty(
        name="Cluster Cleanup",
        description="Nach allen Durchläufen zusätzliche Cluster-Bereinigung (global) ausführen",
        default=True
    )
    cluster_use_pattern: bpy.props.BoolProperty(
        name="Pattern Distanz",
        description="Verwendet max(Patterngröße, MinDist) als effektiven Mindestabstand",
        default=True
    )
