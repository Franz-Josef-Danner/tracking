import bpy

class CLIP_OT_marker_helper_main(bpy.types.Operator):
    bl_idname = "clip.marker_helper_main"
    bl_label = "Marker Helper Main"
    bl_description = "Berechnet Marker-/Tracking-Zielwerte aus den Scene-Properties und startet die Kette"

    # Beibehaltener Multiplikator für adaptives Ziel (Skalierung auf Projektbasis)
    factor: bpy.props.IntProperty(
        name="Faktor",
        description="Multiplikator für marker_basis → marker_adapt",
        default=4, min=1, max=999
    )

    def execute(self, context):
        scene = context.scene

        # --- 1) SOURCE OF TRUTH: UI-Properties aus Scene (setzen Defaults falls nicht vorhanden) ---
        # marker_frame: Ziel-Marker pro Frame (UI)
        marker_basis = int(getattr(scene, "marker_frame", 25))
        # frames_track: Ziel-Tracking-Länge (UI)
        frames_track = int(getattr(scene, "frames_track", 25))
        # error_track: tolerierter Reproj.-Fehler in px (UI)
        error_track = float(getattr(scene, "error_track", 2.0))

        # --- 2) Ableitungen für Marker-Zielkorridor ---
        marker_adapt = int(marker_basis * self.factor * 0.9)
        marker_min   = int(marker_adapt * 0.9)
        marker_max   = int(marker_adapt * 1.1)

        # --- 3) Persistenz für Downstream-Kompatibilität (Key-Value) ---
        # Konsistente Primär-Keys
        scene["marker_basis"] = int(marker_basis)
        scene["marker_adapt"] = int(marker_adapt)
        scene["marker_min"]   = int(marker_min)
        scene["marker_max"]   = int(marker_max)

        # Tracking-Parameter als Keys verfügbar machen
        scene["frames_track"] = int(frames_track)
        scene["error_track"]  = float(error_track)

        # Legacy/Fallback-Keys (sofern Altcode diese noch liest)
        scene["min_marker"]   = int(marker_min)
        scene["max_marker"]   = int(marker_max)

        # --- 4) repeat_frame sauber initialisieren (CollectionProperty vorhanden seit __init__.py) ---
        # Ziel: definierter Startzustand, keine Altlasten aus vorherigen Läufen
        try:
            # Nur wenn Property existiert, leeren – keine Annahmen über Item-Struktur
            _ = scene.repeat_frame
            scene.repeat_frame.clear()
            scene["repeat_frame_initialized"] = True
        except Exception:
            # Falls nicht registriert, sicher weiterlaufen (z. B. in isolierten Tests)
            scene["repeat_frame_initialized"] = False

        # --- 5) Telemetrie / Konsolen-Output für Traceability ---
        msg = (f"[MarkerHelper] basis={marker_basis}, factor={self.factor} → "
               f"adapt={marker_adapt}, min={marker_min}, max={marker_max} | "
               f"frames_track={frames_track}, error_track={error_track}")
        print(msg)
        self.report({'INFO'}, msg)

        # --- 6) Nächster Schritt der Kette (Main-to-Adapt) ---
        try:
            res = bpy.ops.clip.main_to_adapt('INVOKE_DEFAULT', factor=int(self.factor))
            print(f"[MarkerHelper] → main_to_adapt: {res}")
        except Exception as e:
            self.report({'ERROR'}, f"main_to_adapt konnte nicht gestartet werden: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Registration (falls lokal registriert wird)
classes = (CLIP_OT_marker_helper_main,)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
