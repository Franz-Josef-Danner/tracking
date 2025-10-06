import bpy
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Dünner Wrapper: führt nur das eigentliche Tracking über den Helper aus.

    Bewusst KEINE eigene Logik für Frame-Schleifen, Bootstrap oder Frame-Limits.
    Der Operator triggert genau EINEN Tracking-Schritt (sequence=False) für alle
    selektierten Marker im aktiven Clip Editor.

    Motivation:
      - Single-Responsibility: Tracking-Strategien (Loops, Limits, Adaptive Logik)
        gehören in höhere Orchestrierung oder externe Skripte.
      - Dieser Operator bleibt stabil und vorhersagbar.
    """
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Forward (1 Frame)"
    bl_description = "Trackt selektierte Marker genau einen Frame vorwärts (sequence=False)."
    bl_options = {"REGISTER", "INTERNAL"}

    use_sequence: bpy.props.BoolProperty(  # type: ignore
        name="Sequence-Modus",
        description="Wenn aktiv: Blender lässt die Marker bis zum Stop laufen (sequence=True)",
        default=False,
    )

    backwards: bpy.props.BoolProperty(  # type: ignore
        name="Rückwärts",
        description="Marker rückwärts statt vorwärts tracken",
        default=False,
    )

    def execute(self, context):
        clip = context.space_data.clip if getattr(context, "space_data", None) else None
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im CLIP_EDITOR")
            return {'CANCELLED'}

        success = track_forward_selected_markers(
            context,
            sequence=self.use_sequence,
            backwards=self.backwards,
        )
        if not success:
            self.report({'WARNING'}, "Tracking nicht möglich (keine selektierten Marker oder Fehler)")
            return {'CANCELLED'}

        mode = "Sequence" if self.use_sequence else "1 Frame"
        direction = "Rückwärts" if self.backwards else "Vorwärts"
        self.report({'INFO'}, f"Tracking {direction} ({mode}) ausgeführt")
        return {'FINISHED'}


__all__ = ["KAISERLICHTRACKER_OT_track_cycle"]
