import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_detect_adapt(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_adapt"  # ← RICHTIG
    bl_label = "Detect Adapt (einmalig)"
    bl_description = (
        "Führt eine einmalige Marker-Detektion aus: Bootstrap → Detect → Cleanup → Selektieren."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame

        # ============================================
        # Bootstrap: Parameter initialisieren
        # ============================================
        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        md = float(params['md'])
        ma = int(params['ma'])
        tr = float(params['tr'])
        pz = int(params['pz'])
        sz = int(params['sz'])
        hz = params['hz']
        vc = params['vc']

        print("[Kaiserlich Tracker] ================ Einmaliger Detect Start ================")
        print(f"[Kaiserlich Tracker] md={md:.2f} tr={tr:.4f} pz={pz} sz={sz}")

        # ============================================
        # Snapshot vor Detect
        # ============================================
        pre_snapshot = snapshot_active_markers(context)
        baseline_start_tracknames = {m['track'] for m in pre_snapshot}

        # ============================================
        # Detect Features (ein Durchlauf)
        # ============================================
        detect_features(
            context,
            placement='FRAME',
            margin=ma,
            threshold=tr,
            min_distance=int(max(1, round(md)))
        )

        # ============================================
        # Snapshot nach Detect und Differenzbildung
        # ============================================
        post_snapshot = snapshot_active_markers(context)
        alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
        am = len(neue_marker)
        print(f"[Kaiserlich Tracker] Neue Marker erkannt: {am}")

        # ============================================
        # Cleanup der neu erzeugten Marker
        # ============================================
        cleaned_new, deleted_old = cleanup_new_markers(
            context,
            alte_marker,
            neue_marker,
            pz=pz,
            hz=hz,
            vc=vc
        )
        print(f"[Kaiserlich Tracker] Cleanup: {deleted_old} alte Tracks gelöscht; verbleibend neue={len(cleaned_new)}")

        # ============================================
        # Selektion der neu erzeugten Marker
        # ============================================
        clip = context.space_data.clip if getattr(context, 'space_data', None) else None
        selected_new_tracks = 0
        if clip and getattr(clip, 'tracking', None):
            tracking = clip.tracking
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            try:
                for trk in tracking.tracks:
                    trk.select = False
                for new_trk in new_tracks:
                    new_trk.select = True
                selected_new_tracks = len(new_tracks)
                print(f"[Kaiserlich Tracker] Selektion: {selected_new_tracks} neue Tracks selektiert.")
            except Exception as e:
                print(f"[Kaiserlich Tracker] Selektion fehlgeschlagen: {e}")
        else:
            print("[Kaiserlich Tracker] Keine Clip/Tracking Daten für Selektion verfügbar.")

        # ============================================
        # Abschluss
        # ============================================
        self.report({'INFO'}, (
            f"Fertig: Neue Marker={am} | Cleanup gelöscht={deleted_old} | "
            f"Selektiert={selected_new_tracks} | md={md:.2f} | tr={tr:.4f}"
        ))
        print("[Kaiserlich Tracker] ================ Detect Zyklus Ende ==================")
        return {'FINISHED'}
