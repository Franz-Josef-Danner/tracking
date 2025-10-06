import bpy

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Trackt alle existierenden Marker über einen Frame-Bereich.

    Einfacher Automations-Wrapper um bpy.ops.clip.track_markers. Nutzt den aktuell
    aktiven Movie Clip Editor Kontext (aus dem heraus der Button gedrückt wird).
    """
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Cycle"
    bl_description = "Track vorhandene Marker über den angegebenen Frame-Bereich vorwärts"
    bl_options = {"REGISTER", "INTERNAL"}

    frame_start: bpy.props.IntProperty(  # type: ignore
        name="Start Frame",
        description="Erster Frame der Tracking-Sequenz (Standard = aktueller Frame)",
        default=-1,
    )
    frame_end: bpy.props.IntProperty(  # type: ignore
        name="End Frame",
        description="Letzter Frame der Tracking-Sequenz (Standard = Szenenende)",
        default=-1,
    )
    sequence: bpy.props.BoolProperty(  # type: ignore
        name="Sequence",
        description="Verwendet Blender 'sequence' Modus (folgt Schlüsselbilder-Reihenfolge)",
        default=False,
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip if getattr(context, "space_data", None) else None
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip zum Tracken")
            return {'CANCELLED'}

        start = self.frame_start if self.frame_start >= 0 else scene.frame_current
        end = self.frame_end if self.frame_end >= 0 else scene.frame_end
        if end < start:
            self.report({'WARNING'}, f"Ungültiger Frame-Bereich: {start}>{end}")
            return {'CANCELLED'}

        total_tracked = 0
        print(f"[Kaiserlich Tracker] ===== Track Cycle Start: {start}->{end} sequence={self.sequence} =====")
        current_orig = scene.frame_current
        try:
            for f in range(start, end + 1):
                scene.frame_set(f)
                try:
                    res = bpy.ops.clip.track_markers(backwards=False, sequence=self.sequence)
                    if 'CANCELLED' not in res:
                        total_tracked += 1
                except Exception as e:
                    print(f"[Kaiserlich Tracker] Track Fehler bei Frame {f}: {e}")
            msg = f"Tracking abgeschlossen: {total_tracked} Frames verarbeitet"
            self.report({'INFO'}, msg)
            print(f"[Kaiserlich Tracker] {msg}")
        finally:
            scene.frame_set(current_orig)
        print("[Kaiserlich Tracker] ===== Track Cycle Ende =====")
        return {'FINISHED'}
