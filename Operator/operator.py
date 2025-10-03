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

        # Arbeitskopie für adaptive Parameter
        tr = base_params['tr']
        md = base_params['md']
        pz = base_params['pz']
        sz = base_params['sz']

        MAX_ITER = 5
        iteration = 0
        summary_deleted = 0
        last_new_count = 0

        while iteration < MAX_ITER:
            iteration += 1
            print(f"[Kaiserlich Tracker] === Cyclus Iteration {iteration} === tr={tr} md={md} pz={pz} sz={sz}")

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
            print(f"[Kaiserlich Tracker] am (Anzahl neue Marker) = {am}")

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
            if comparison_log:
                print("[Kaiserlich Tracker] Marker Vergleich:")
                for line in comparison_log:
                    print("   ", line)

            # Cleanup Paare bilden nur für AMA
            from ..Helper.cleaneup import MarkerPair
            marker_pairs = []
            for nm in new_markers:
                old = old_by_track.get(nm.track_name)
                if old:
                    marker_pairs.append(MarkerPair(
                        track_name=nm.track_name,
                        old_co=(old.co_x, old.co_y),
                        new_co=(nm.co_x, nm.co_y)
                    ))
            if marker_pairs:
                deleted_count = cleaneup.cleanup_markers(context, marker_pairs, md=md, hz=hz, vc=vc)
                summary_deleted += deleted_count
            else:
                deleted_count = 0

            # Abbruchbedingungen / Adaptive Logik
            if am == 0:
                print("[Kaiserlich Tracker] Keine neuen Marker - Ende.")
                break
            if tr < 0.1:
                print("[Kaiserlich Tracker] Schwelle < 0.1 - Ende.")
                break
            # Bereichslogik
            if am > ug:
                if am < og:
                    # zwischen ug und og: Parameter fein anpassen
                    tr *= 0.15
                    if tr < 0.1:
                        print("[Kaiserlich Tracker] tr unter 0.1 nach Anpassung - Ende.")
                        break
                    pz = max(2, int(pz * 1.1))
                    sz = max(4, int(pz * 2))
                    print(f"[Kaiserlich Tracker] Anpassung: tr={tr:.4f} pz={pz} sz={sz}")
                    continue  # neuer Zyklus
                else:
                    # am >= og -> md neu kalibrieren und alle neuen Marker löschen
                    ratio = za / max(am, 1)
                    if ratio > 0:
                        md = int(md / ratio) if ratio != 0 else md
                    print(f"[Kaiserlich Tracker] Neue md (over-range) = {md}")
                    for nm in new_markers:
                        delete.delete_track(context, nm.track_name)
                    continue  # neuer Zyklus
            else:
                # am <= ug -> md anpassen und neue Marker löschen
                ratio = za / max(am, 1)
                if ratio > 0:
                    md = int(md / ratio) if ratio != 0 else md
                print(f"[Kaiserlich Tracker] Neue md (under-range) = {md}")
                for nm in new_markers:
                    delete.delete_track(context, nm.track_name)
                continue

        # Abschlussreport
        self.report({'INFO'}, (
            f"Detect Zyklus beendet nach {iteration} Iterationen | del_total={summary_deleted} "
            f"tr={tr:.4f} md={md} pz={pz} sz={sz} og={og} ug={ug}"
        ))
        return {'FINISHED'}

classes = [KAISERLICH_OT_detect_cyclus]

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
