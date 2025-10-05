import bpy
from ..Helper import bootstrap, snapshot, newmarker, detect, compare, cleaneup, delete

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = 'kaiserlich.detect_cyclus'
    bl_label = 'Detect Cyclus'
    bl_description = 'Erkennt den Zyklus basierend auf den Einstellungen'

    def execute(self, context):
        scene = context.scene
        # Sicherstellen, dass Property existiert
        props = getattr(scene, 'kaiserlich_tracker', None)
        if props is None or not hasattr(props, 'marker_per_frame'):
            self.report({'ERROR'}, 'Property marker_per_frame nicht gefunden – bitte Add-on neu laden.')
            return {'CANCELLED'}

        ef_raw = props.marker_per_frame
        try:
            ef = int(ef_raw)
        except Exception:
            self.report({'ERROR'}, f'Ungueltiger Eingabewert: {ef_raw}')
            return {'CANCELLED'}

        values = bootstrap.run(context, ef)
        if not values:
            self.report({'ERROR'}, 'Keine Berechnungen – kein aktiver Clip?')
            return {'CANCELLED'}

        # Zyklische Schleife gemäß Vorgabe
        za = values['za']
        ug = values['ug']
        md_current = values['md']  # dynamisch anpassbar

        surviving = 0
        iteration = 0
        while True:
            iteration += 1
            print(f'=== Zyklus Start Iteration {iteration} (md={md_current}) ===')
            # Snapshot (Baseline alte Marker)
            snapshot.run(context, values)
            # Vorbereitung neuer Marker (Platzhalter)
            newmarker.run(context, values)
            # Detection mit aktuellem md
            detect.run(context, tr=values['tr'], md=md_current, ma=values['ma'])
            # Vergleich alt / neu
            cmp_result = compare.run(context)
            # Cleanup (löscht zu nahe neue Marker) – Werte dict mit aktuellem md versorgen
            values['md'] = md_current
            surviving = cleaneup.run(
                context,
                values,
                new_tracks=cmp_result.get('new_tracks'),
                old_tracks=cmp_result.get('old_tracks')
            )
            am = surviving  # Anzahl neuer Marker nach Cleanup
            print(f'[Cycle] Neue Marker (am) nach Cleanup: {am} (ug={ug}, za={za})')
            # Abbruchbedingung: genügend neue Marker
            if am > ug:
                print(f'[Cycle] am ({am}) > ug ({ug}) -> Schleife beendet')
                break
            # Keine neuen Marker -> kein Fortschritt mehr
            if am == 0:
                print('[Cycle] Keine neuen Marker (am=0) -> Schleife beendet')
                break
            # md anpassen: md = md / (za / am) = md * (am / za)
            if za > 0:
                new_md = md_current * (am / za)
                # Sanity Clamp (verhindere zu kleine Werte)
                if new_md < 1:
                    new_md = 1
                print(f'[Cycle] md Anpassung: alt={md_current} neu={new_md}')
                md_current = new_md
            else:
                print('[Cycle] za=0 -> md unverändert')
            # Neue Marker auf aktuellem Frame löschen, um nächste Iteration frisch zu generieren
            try:
                clip = bpy.context.edit_movieclip
                frame_cur = context.scene.frame_current
                if clip:
                    candidate_names = cmp_result.get('new_names', set())
                    # Filter: existiert Track noch & hat Marker auf Frame
                    existing_names = []
                    for t in clip.tracking.tracks:
                        if t.name in candidate_names:
                            try:
                                has_marker = any(m.frame == frame_cur for m in t.markers)
                            except Exception:
                                has_marker = False
                            if has_marker:
                                existing_names.append(t.name)
                    if existing_names:
                        print(f'[Cycle] Lösche Marker auf Frame {frame_cur} für neue Tracks: {existing_names}')
                        delete.delete_markers_by_names(frame_cur, existing_names)
                    else:
                        print('[Cycle] Keine überlebenden neuen Marker zum Löschen gefunden')
            except Exception as e:
                print(f'[Cycle] Fehler beim Löschschritt: {e}')
            # Weiter zur nächsten Iteration
        self.report({'INFO'}, f'Zyklus beendet – neue Marker zuletzt: {surviving} (ef={ef})')
        return {'FINISHED'}

classes = (KAISERLICH_OT_detect_cyclus,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
