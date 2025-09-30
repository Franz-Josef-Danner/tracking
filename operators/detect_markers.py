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

        # Multi-Pass Detect Parameter
        start_threshold = 1.0
        min_threshold = 0.0001
        factor = 0.5
        max_passes = 32  # Sicherheitsgrenze

        passes = 0
        current = start_threshold
        clip = None
        try:
            clip = area.spaces.active.clip
        except Exception:  # noqa: BLE001
            clip = None

        tracks_before = len(clip.tracking.tracks) if clip else -1
        added_each_pass = []  # Liste von Tupeln (threshold, hinzugefügt, hinweis)

        # Prüfen ob threshold-Property existiert
        has_threshold = False
        try:
            rna = bpy.ops.clip.detect_features.get_rna_type()
            has_threshold = 'threshold' in rna.properties.keys()
        except Exception:  # noqa: BLE001
            has_threshold = False

        def run_detect(thr, override_threshold=True):
            """Führt detect_features aus. Gibt (added, used_thr, note)."""
            prev = len(clip.tracking.tracks) if clip else 0
            note = ''
            try:
                if has_threshold and override_threshold:
                    bpy.ops.clip.detect_features(threshold=thr)
                else:
                    bpy.ops.clip.detect_features()
                    if override_threshold and not has_threshold:
                        note = 'threshold nicht unterstützt'
            except TypeError:
                # Falls trotz has_threshold ein Typfehler kommt -> einmal ohne und dann als nicht unterstützt markieren
                if override_threshold:
                    bpy.ops.clip.detect_features()
                    note = 'threshold TypeError'
                else:
                    raise
            new_total = len(clip.tracking.tracks) if clip else prev
            return new_total - prev, thr, note

        try:
            with context.temp_override(area=area, region=region):
                if not has_threshold:
                    # Nur ein einziger Pass möglich
                    added, thr, note = run_detect(current, override_threshold=False)
                    passes = 1
                    added_each_pass.append((thr, added, note or 'kein threshold Param'))
                else:
                    while current >= min_threshold and passes < max_passes:
                        added, thr, note = run_detect(current, override_threshold=True)
                        added_each_pass.append((thr, added, note))
                        passes += 1
                        current *= factor
        except AttributeError:
            # Fallback ohne temp_override
            override = context.copy()
            override['area'] = area
            override['region'] = region
            # Einfacher Fallback: keine differenzierten Kontexte mehr
            if not has_threshold:
                prev = len(clip.tracking.tracks) if clip else 0
                try:
                    bpy.ops.clip.detect_features(override)
                except Exception as e:  # noqa: BLE001
                    self.report({'ERROR'}, f'Fallback detect failed: {e}')
                    return {'CANCELLED'}
                new_total = len(clip.tracking.tracks) if clip else prev
                added_each_pass.append((start_threshold, new_total - prev, 'fallback ohne threshold'))
                passes = 1
            else:
                current = start_threshold
                while current >= min_threshold and passes < max_passes:
                    prev = len(clip.tracking.tracks) if clip else 0
                    try:
                        bpy.ops.clip.detect_features(override, threshold=current)
                    except TypeError:
                        try:
                            bpy.ops.clip.detect_features(override)
                        except Exception as e:  # noqa: BLE001
                            self.report({'WARNING'}, f'Fallback Pass {passes+1} Fehler: {e}')
                            break
                    except Exception as e:  # noqa: BLE001
                        self.report({'WARNING'}, f'Fallback Pass {passes+1} Fehler: {e}')
                        break
                    new_total = len(clip.tracking.tracks) if clip else prev
                    added_each_pass.append((current, new_total - prev, 'fallback'))
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
        for thr, added, note in added_each_pass:
            base = f'{thr:.5f}:{added}'
            if note:
                base += f' ({note})'
            summary_parts.append(base)
        summary = ', '.join(summary_parts) if summary_parts else 'keine Marker hinzugefügt'

        self.report({'INFO'}, f'{passes} Durchläufe, hinzugefügt: {total_added} (pro Pass: {summary})')
        return {'FINISHED'}
