import bpy

class TRACKING_OT_detect_markers(bpy.types.Operator):
    bl_idname = "tracking.detect_markers"
    bl_label = "Detect Markers"
    bl_description = "Führt Detect Features im Movie Clip Editor aus und setzt Marker"
    bl_options = {"REGISTER", "UNDO"}

    placement = bpy.props.EnumProperty(
        name="Platzierung",
        description="Wo neue Marker erkannt werden dürfen",
        items=[
            ('FRAME', 'Aktueller Frame', ''),
            ('TRACKS', 'Nur existierende Tracks erweitern', ''),
            ('MANUAL', 'Nur manuell definierter Bereich', '')
        ],
        default='FRAME'
    )

    margin = bpy.props.IntProperty(
        name="Rand (px)",
        description="Schutzabstand zu Bildrand bei der Erkennung",
        default=16,
        min=0,
        max=128
    )

    threshold = bpy.props.FloatProperty(
        name="Schwelle",
        description="Feature Erkennungs-Schwelle (höher = weniger Marker)",
        default=0.5,
        min=0.01,
        max=1.0
    )

    def execute(self, context):
        area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
        if area is None:
            self.report({'ERROR'}, 'Kein Movie Clip Editor Bereich gefunden')
            return {'CANCELLED'}

        override = context.copy()
        override['area'] = area
        override['region'] = next(r for r in area.regions if r.type == 'WINDOW')

        # Set properties on space
        space = area.spaces.active
        # Some parameters might not map 1:1; using detect_features operator directly
        try:
            bpy.ops.clip.detect_features(override, placement=self.placement, margin=self.margin, threshold=self.threshold)
        except TypeError:
            # Fallback falls Parameter nicht unterstützt werden (je nach Blender Version)
            try:
                bpy.ops.clip.detect_features(override)
            except Exception as e:  # noqa: BLE001
                self.report({'ERROR'}, f'Detect Features fehlgeschlagen: {e}')
                return {'CANCELLED'}

        return {'FINISHED'}
