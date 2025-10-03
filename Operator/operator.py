import bpy
from ..Helper import bootstrap, snapshot, detect, newmarker

class KAISERLICH_OT_detect_cyclus(bpy.types.Operator):
    bl_idname = "kaiserlich.detect_cycle"  # ID bleibt technisch gleich für Kompatibilität
    bl_label = "Detect Cyclus"
    bl_description = "Führt den Erkennungs-Cyclus aus"

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_marker_per_frame
        # 1) Parameter berechnen
        params = bootstrap.run(context, ef)
        # 2) Vor Detect: vorhandene Track-Namen merken (Cyclus Start)
        pre_clip = getattr(context.space_data, 'clip', None) if context.space_data and context.space_data.type == 'CLIP_EDITOR' else None
        old_names = []
        if pre_clip:
            try:
                old_names = [t.name for t in pre_clip.tracking.tracks]
            except Exception:
                old_names = []
        # 3) Snapshot der aktuell aktiven Marker aufnehmen (vor Detect)
        markers = snapshot.capture_current_frame_markers(context)
        # 4) Feature Detection mit tr, md, ma, pz, sz
        detect.detect_features(context, params)
        # 5) Neue Marker/Tracks nach Detect erfassen
        new_markers = newmarker.capture_new_tracks(context, old_names)

        # 6) Vergleich alte vs. neue Marker (Positionsvergleich pro Track-Name)
        comparison_log = []
        # Map track -> marker snapshot (alt)
        old_by_track = {m.track_name: m for m in markers}
        for nm in new_markers:
            old = old_by_track.get(nm.track_name)
            if old:
                # AMA (alter Marker vorhanden) => vergleichen Koordinaten
                if abs(old.co_x - nm.co_x) < 1e-6 and abs(old.co_y - nm.co_y) < 1e-6:
                    status = "AMA (gleich)"
                else:
                    status = "AMA (verschoben)"
                comparison_log.append(f"{status}: {nm.track_name} alt=({old.co_x:.4f},{old.co_y:.4f}) neu=({nm.co_x:.4f},{nm.co_y:.4f})")
            else:
                comparison_log.append(f"NM: {nm.track_name} neu=({nm.co_x:.4f},{nm.co_y:.4f})")

        if comparison_log:
            print("[Kaiserlich Tracker] Marker Vergleich:")
            for line in comparison_log:
                print("   ", line)
        tr = params.get('tr')
        md = params.get('md')
        ma = params.get('ma')
        pz = params.get('pz')
        sz = params.get('sz')
        self.report({'INFO'}, (
            f"Detect Cyclus fertig: alt={len(markers)} neu={len(new_markers)} | ef={ef} "
            f"tr={tr} md={md} ma={ma} pz={pz} sz={sz}"
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
