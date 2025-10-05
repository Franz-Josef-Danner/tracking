import bpy
from ..Helper import bootstrap, snapshot, detect, newmarker, cleaneup, marker_size, delete

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = "kaiserlich.detect_cycle"  # ID bleibt technisch gleich für Kompatibilität
    bl_label = "Detect Cyclus"
    bl_description = "Führt den Erkennungs-Cyclus aus"

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_marker_per_frame

        # Initialer Bootstrap (liefert og/ug, za etc.)
        base_params = bootstrap.run(context, ef)
        hz = base_params['hz']
        vc = base_params['vc']
        og = base_params['og']  # ober Grenze
        ug = base_params['ug']  # unter Grenze
        za = base_params['za']
        ma = base_params['ma']

        # Arbeitskopie für adaptive Parameter (ohne Obergrenze für Iterationen)
        tr = base_params['tr']
        md = base_params['md']
        pz = base_params['pz']
        sz = base_params['sz']

        iteration = 0
        summary_deleted = 0

        while True:
            iteration += 1

            # Anwenden der aktuellen Markergrößen falls geändert
            marker_size.apply_marker_sizes(context, pz, sz)

            # Tracknamen vor Detect
            pre_clip = getattr(context.space_data, 'clip', None) if context.space_data and context.space_data.type == 'CLIP_EDITOR' else None
            old_names = []
            if pre_clip:
                try:
                    old_names = [t.name for t in pre_clip.tracking.tracks]
                except Exception:
                    old_names = []

            # Snapshot vor Detect
            old_markers = snapshot.capture_current_frame_markers(context)

            # Feature Detection (nutzt tr, md, ma -> wir geben sie über params kompatibel weiter)
            detect.detect_features(context, {
                'tr': tr,
                'md': md,
                'ma': ma,
                'pz': pz,
                'sz': sz,
            })

            # Neue Marker (nur wirklich neu entstandene Tracks)
            new_markers = newmarker.capture_new_tracks(context, old_names)
            am = len(new_markers)
            print(f"am = {am}")

            # Post-Snapshot für AMA-Paare (Tracks, die schon vorher existierten)
            post_markers = snapshot.capture_current_frame_markers(context)
            old_by_name = {m.track_name: m for m in old_markers}
            post_by_name = {m.track_name: m for m in post_markers}

            # AMA-Paare = Track existierte vorher und nachher
            from ..Helper.cleaneup import MarkerPair
            marker_pairs = []
            for tname, old_m in old_by_name.items():
                new_m = post_by_name.get(tname)
                if new_m:
                    marker_pairs.append(MarkerPair(
                        track_name=tname,
                        old_co=(old_m.co_x, old_m.co_y),
                        new_co=(new_m.co_x, new_m.co_y)
                    ))
            # Distanz-Prüfung nur auf AMA-Paare (neue Tracks ohne Vorgänger werden nicht geprüft)
            cleaneup.cleanup_markers(context, marker_pairs, md=md, hz=hz, vc=vc)

            # Vergleich alt/neu
            old_by_track = {m.track_name: m for m in old_markers}
            comparison_log = []
            for nm in new_markers:
                old = old_by_track.get(nm.track_name)
                if old:
                    if abs(old.co_x - nm.co_x) < 1e-6 and abs(old.co_y - nm.co_y) < 1e-6:
                        status = "AMA (gleich)"
                    else:
                        status = "AMA (verschoben)"
                    comparison_log.append(
                        f"{status}: {nm.track_name} alt=({old.co_x:.4f},{old.co_y:.4f}) neu=({nm.co_x:.4f},{nm.co_y:.4f})"
                    )
                else:
                    comparison_log.append(
                        f"NM: {nm.track_name} neu=({nm.co_x:.4f},{nm.co_y:.4f})"
                    )
            # Vergleichslog entfernt

            # (Kein Frühabbruch mehr – voller Zyklus gemäß Vorgabe)

            # Abbruchbedingungen / Adaptive Logik
            # Falls keine neuen Marker: aggressiveres Nachjustieren statt sofortigem Ende
            if am == 0:
                tr *= 0.5  # Schwelle senken um mehr Features zuzulassen
                pz = max(2, int(pz * 1.05))  # leicht größere Pattern Size
                sz = max(4, int(pz * 2))
                if tr < 0.01:
                    break
                print(f"pz = {pz}")
                continue

            if tr < 0.01:
                break
            # Bereichslogik
            if am > ug:
                if am < og:
                    # zwischen ug und og: Parameter fein anpassen
                    tr *= 0.15
                    if tr < 0.01:
                        break
                    pz = max(2, int(pz * 1.1))
                    sz = max(4, int(pz * 2))
                    print(f"pz = {pz}")
                    continue  # neuer Zyklus
                else:
                    # am >= og -> md neu kalibrieren und alle neuen Marker löschen
                    ratio = za / max(am, 1)
                    if ratio > 0:
                        md = int(md / ratio) if ratio != 0 else md
                    print(f"md = {md}")
                    for nm in new_markers:
                        delete.delete_marker_frame(context, nm.track_name, context.scene.frame_current)
                    continue  # neuer Zyklus
            else:
                # am <= ug -> md anpassen und neue Marker löschen
                ratio = za / max(am, 1)
                if ratio > 0:
                    md = int(md / ratio) if ratio != 0 else md
                print(f"md = {md}")
                for nm in new_markers:
                    delete.delete_marker_frame(context, nm.track_name, context.scene.frame_current)
                continue

        # Abschlussreport
        self.report({'INFO'}, (
            f"Detect Zyklus beendet nach {iteration} Iterationen | del_total={summary_deleted} "
            f"tr={tr:.4f} md={md} pz={pz} sz={sz} og={og} ug={ug}"
        ))
        return {'FINISHED'}

class KAISERLICH_OT_delete_marker(bpy.types.Operator):
    """Löscht Marker im aktuellen Frame.

    Wenn ein Track-Name gesetzt ist (UI-Feld), wird nur dessen Marker im aktuellen Frame gelöscht.
    Ist kein Name gesetzt, werden Marker aller Tracks im aktuellen Frame (falls vorhanden) gelöscht.
    """
    bl_idname = "kaiserlich.delete_marker"
    bl_label = "Delete Marker Frame"
    bl_description = "Löscht Marker im aktuellen Frame (optional nur eines Tracks)"

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        track_name = getattr(scene, 'kaiserlich_delete_track_name', '').strip()

        space = context.space_data
        if not space or space.type != 'CLIP_EDITOR':
            self.report({'WARNING'}, "Kein Clip Editor aktiv")
            return {'CANCELLED'}
        clip = getattr(space, 'clip', None)
        if not clip:
            self.report({'WARNING'}, "Kein aktiver Clip")
            return {'CANCELLED'}

        tracking = clip.tracking
        deleted = 0
        if track_name:
            if delete.delete_marker_frame(context, track_name, frame):
                deleted = 1
        else:
            for tr in tracking.tracks:
                if delete.delete_marker_frame(context, tr.name, frame):
                    deleted += 1

        self.report({'INFO'}, f"Marker gelöscht: {deleted} (Frame {frame})")
        return {'FINISHED'}

classes = [KAISERLICH_OT_detect_cyclus, KAISERLICH_OT_delete_marker]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
