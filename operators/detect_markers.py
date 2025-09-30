import bpy


class TRACKING_OT_detect_markers(bpy.types.Operator):
    bl_idname = "tracking.detect_markers"
    bl_label = "Detect Markers"
    bl_description = (
        "Mehrfaches Feature-Detect: Startet bei Threshold=1.0 und halbiert bis < 0.0001.\n"
        "So werden erst sehr starke, dann zunehmend schwächere Features hinzugefügt."
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

        # Multi-Pass Detect
        start_threshold = 1.0
        min_threshold = 0.0001
        factor = 0.5
        max_passes = 32  # Sicherheitsgrenze

        passes = 0
        current = start_threshold
        clip = None
        # Versuche Clip zu ermitteln (falls im aktiven Space vorhanden)
        try:
            clip = area.spaces.active.clip
        except Exception:  # noqa: BLE001
            clip = None

        tracks_before = len(clip.tracking.tracks) if clip else -1
        added_each_pass = []

        try:
            with context.temp_override(area=area, region=region):
                while current >= min_threshold and passes < max_passes:
                    prev_tracks = len(clip.tracking.tracks) if clip else 0
                    try:
                        result = bpy.ops.clip.detect_features(threshold=current)
                        # Falls Operator Rückgabe nicht FINISHED liefert, abbrechen
                        if result not in {{'FINISHED', 'CANCELLED'}}:
                            pass
                    except TypeError:
                        # Threshold-Argument wird nicht unterstützt -> einmal ohne und dann abbrechen
                        if passes == 0:
                            bpy.ops.clip.detect_features()
                        break
                    except Exception as e:  # noqa: BLE001
                        self.report({'WARNING'}, f'Pass {passes+1} bei Threshold {current:.6f} fehlgeschlagen: {e}')
                        break

                    new_tracks = len(clip.tracking.tracks) if clip else prev_tracks
                    added = new_tracks - prev_tracks
                    added_each_pass.append((current, added))
                    passes += 1
                    current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            current = start_threshold
            while current >= min_threshold and passes < max_passes:
                prev_tracks = len(clip.tracking.tracks) if clip else 0
                try:
                    bpy.ops.clip.detect_features(override, threshold=current)
                except TypeError:
                    if passes == 0:
                        bpy.ops.clip.detect_features(override)
                    break
                except Exception as e:  # noqa: BLE001
                    self.report({'WARNING'}, f'Pass {passes+1} (Fallback) fehlgeschlagen: {e}')
                    break
                new_tracks = len(clip.tracking.tracks) if clip else prev_tracks
                added_each_pass.append((current, new_tracks - prev_tracks))
                passes += 1
                current *= factor
        except Exception as e:  # noqa: BLE001
            self.report({'ERROR'}, f'Unerwarteter Fehler: {e}')
            return {'CANCELLED'}

        if clip:
            total_added = len(clip.tracking.tracks) - tracks_before
        else:
            total_added = -1

        summary_parts = []
        for thr, added in added_each_pass:
            summary_parts.append(f'{thr:.5f}:{added}')
        summary = ', '.join(summary_parts) if summary_parts else 'keine Marker hinzugefügt'

        self.report({'INFO'}, f'{passes} Durchläufe, hinzugefügt: {total_added} (pro Pass: {summary})')
        return {'FINISHED'}
