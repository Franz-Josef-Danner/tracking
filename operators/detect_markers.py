import bpy


class TRACKING_OT_detect_markers(bpy.types.Operator):
    bl_idname = "tracking.detect_markers"
    bl_label = "Detect Markers"
    bl_description = (
        "Ruft den eingebauten 'Detect Features' Operator auf und erzeugt automatisch Marker.\n"
        "Diese Minimal-Variante nutzt die Standardparameter der aktuellen Blender-Version,\n"
        "um Versionsinkompatibilitäten (Parameteränderungen) zu vermeiden."
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # Robuste Suche nach einem Movie Clip Editor (auch falls mehrere Fenster)
        area = None
        for window in context.window_manager.windows:
            scr = window.screen
            if not scr:
                continue
            area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
            if area:
                break

        if area is None:
            self.report({'ERROR'}, 'Kein Movie Clip Editor Bereich gefunden (öffne einen Clip Editor).')
            return {'CANCELLED'}

        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region is None:
            self.report({'ERROR'}, 'Keine gültige WINDOW Region im Clip Editor gefunden.')
            return {'CANCELLED'}

        try:
            # Neues API Pattern (>= 3.x) – Kontext temporär überschreiben
            with context.temp_override(area=area, region=region):
                bpy.ops.clip.detect_features()
        except AttributeError:
            # Fallback für sehr alte Versionen ohne temp_override (sollte bei 4.4 nicht nötig sein)
            override = context.copy()
            override['area'] = area
            override['region'] = region
            try:
                bpy.ops.clip.detect_features(override)
            except Exception as e:  # noqa: BLE001
                self.report({'ERROR'}, f'Detect Features fehlgeschlagen: {e}')
                return {'CANCELLED'}
        except Exception as e:  # noqa: BLE001
            self.report({'ERROR'}, f'Fehler beim Ausführen: {e}')
            return {'CANCELLED'}

        self.report({'INFO'}, 'Marker erkannt (Standardparameter).')
        return {'FINISHED'}
