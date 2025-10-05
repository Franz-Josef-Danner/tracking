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

            # Neue Marker nach Detect
            new_markers = newmarker.capture_new_tracks(context, old_names)
            am = len(new_markers)
            print(f"[KT][cycle] frame={context.scene.frame_current} old_count={len(old_markers)} new_count={am}")
            if old_markers:
                print(f"[KT][cycle] old_names_sample={[m.track_name for m in old_markers[:5]]}")
            if new_markers:
                print(f"[KT][cycle] new_names_sample={[m.track_name for m in new_markers[:5]]}")

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

            # Neue Pair-Logik: Nächstgelegener alter Marker je neuem Marker (Pixel-Distanz)
            from ..Helper.cleaneup import MarkerPair
            marker_pairs = []
            if old_markers and new_markers:
                # Precompute old coords list
                old_list = list(old_markers)
                for nm in new_markers:
                    best = None
                    best_dx = None
                    best_dy = None
                    for om in old_list:
                        dx = abs((nm.co_x - om.co_x) * hz)
                        dy = abs((nm.co_y - om.co_y) * vc)
                        if best is None or (dx + dy) < (best_dx + best_dy):
                            best = om
                            best_dx = dx
                            best_dy = dy
                    if best is not None:
                        close = (best_dx < md) or (best_dy < md)
                        print(f"[KT][pair] new={nm.track_name} best_old={best.track_name} dx={best_dx:.1f} dy={best_dy:.1f} md={md} close={close}")
                        if close:
                            marker_pairs.append(MarkerPair(
                                track_name=nm.track_name,  # wir löschen den NEUEN Track falls zu nah
                                old_co=(best.co_x, best.co_y),
                                new_co=(nm.co_x, nm.co_y)
                            ))
            else:
                if not old_markers:
                    print("[KT][pair] skip: keine alten Marker für Distanzvergleich verfügbar")
            print(f"[KT][cycle] dist_pairs={len(marker_pairs)} (Close-Kandidaten für Löschung)")
            # Cleanup jetzt immer aufrufen, damit Logging sichtbar ist, auch wenn 0 Paare
            deleted_count = cleaneup.cleanup_markers(context, marker_pairs, md=md, hz=hz, vc=vc)
            summary_deleted += deleted_count

            # Abbruchbedingungen / Adaptive Logik
            # Falls keine neuen Marker: aggressiveres Nachjustieren statt sofortigem Ende
            if am == 0:
                tr *= 0.5  # Schwelle senken um mehr Features zuzulassen
                pz = max(2, int(pz * 1.05))  # leicht größere Pattern Size
                sz = max(4, int(pz * 2))
                if tr < 0.01:
                    break
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
                    continue  # neuer Zyklus
                else:
                    # am >= og -> md neu kalibrieren und alle neuen Marker löschen
                    ratio = za / max(am, 1)
                    if ratio > 0:
                        md = int(md / ratio) if ratio != 0 else md
                    for nm in new_markers:
                        delete.delete_marker_frame(context, nm.track_name, context.scene.frame_current)
                    continue  # neuer Zyklus
            else:
                # am <= ug -> md anpassen und neue Marker löschen
                ratio = za / max(am, 1)
                if ratio > 0:
                    md = int(md / ratio) if ratio != 0 else md
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
