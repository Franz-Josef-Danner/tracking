import bpy
from bpy.types import Operator

# --- Core: reine Zähllogik als Helper (beibehaltet für Wiederverwendung) ---
def find_low_marker_frame_core(clip, marker_basis=20, frame_start=None, frame_end=None):
    """Liefert den ersten Frame < marker_basis oder None (pure function, keine Seiteneffekte)."""
    tracking = clip.tracking
    tracks = tracking.tracks

    if frame_start is None:
        frame_start = clip.frame_start
    if frame_end is None:
        frame_end = bpy.context.scene.frame_end

    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {marker_basis}")

    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            marker = track.markers.find_frame(frame)
            if marker:
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < marker_basis:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Kein Frame mit zu wenigen Markern gefunden.")
    return None


class CLIP_OT_find_low_marker(Operator):
    """Sucht den ersten Frame unter 'marker_basis'.
       If/Else: Treffer → jump_to_frame; kein Treffer → clean_error_tracks."""
    bl_idname = "clip.find_low_marker"
    bl_label = "Find Low Marker Frame"
    bl_options = {"INTERNAL"}  # nicht im Undo-Stack relevant

    # Params: bewusst lokal (kein Schreiben in scene[] außer goto_frame bei Treffer)
    use_scene_basis: bpy.props.BoolProperty(
        name="Scene-Basis verwenden",
        description="marker_basis aus Scene['marker_basis'] lesen (Fallback: Default)",
        default=True
    )
    marker_basis: bpy.props.IntProperty(
        name="Mindestmarker pro Frame",
        description="Schwellwert für aktive Marker",
        default=20, min=1, max=100000
    )
    frame_start: bpy.props.IntProperty(
        name="Frame Start (optional)",
        default=-1, min=-1, description="-1 = automatisch (clip.frame_start)"
    )
    frame_end: bpy.props.IntProperty(
        name="Frame End (optional)",
        default=-1, min=-1, description="-1 = automatisch (scene.frame_end)"
    )

    def _get_clip(self, context):
        space = getattr(context, "space_data", None)
        if space and getattr(space, "clip", None):
            return space.clip
        return bpy.data.movieclips[0] if bpy.data.movieclips else None

    def execute(self, context):
        clip = self._get_clip(context)
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        scene = context.scene
        basis = int(scene.get("marker_basis", self.marker_basis)) if self.use_scene_basis else int(self.marker_basis)

        fs = None if self.frame_start < 0 else self.frame_start
        fe = None if self.frame_end < 0 else self.frame_end

        # Kernlogik (keine Seiteneffekte):
        low_frame = find_low_marker_frame_core(clip, marker_basis=basis, frame_start=fs, frame_end=fe)

        # --- Neuer If/Else-Flow ---
        if low_frame is not None:
            # 1) Ziel-Frame in Scene-Prop ablegen
            scene["goto_frame"] = int(low_frame)
            print(f"[MarkerCheck] Treffer: Low-Marker-Frame {low_frame}. Übergabe an jump_to_frame …")

            # 2) Eigenständigen Jump-Operator starten (nutzt eigenen CLIP-Override)
            try:
                # target_frame optional direkt mitgeben (robuster als nur Scene-Prop)
                bpy.ops.clip.jump_to_frame('EXEC_DEFAULT', target_frame=int(low_frame))
            except Exception as ex:
                self.report({'ERROR'}, f"jump_to_frame fehlgeschlagen: {ex}")
                return {'CANCELLED'}

            return {'FINISHED'}

        # Kein Treffer → Solve-Pipeline starten
        print("[MarkerCheck] Keine Low-Marker-Frames gefunden. Starte Kamera-Solve.")
        try:
            # Modal-Operator, kümmert sich intern um Override/Timer/Status
            bpy.ops.clip.clean_error_tracks('INVOKE_DEFAULT')
        except Exception as ex:
            self.report({'ERROR'}, f"Solve-Start fehlgeschlagen: {ex}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Optional: lokale Registration
classes = (CLIP_OT_find_low_marker,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

# Hinweis: Bestehende Imports können weiterhin die Kernfunktion verwenden:
#   find_low_marker_frame_core(...)
