# detect_adapt_operator.py
import bpy
import time

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names

class KAISERLICHTRACKER_OT_detect_adapt(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_adapt"
    bl_label = "Detect Adapt (einmalig)"
    bl_description = (
        "Führt eine Marker-Detektion aus, bis die Zielanzahl aus "
        "'kaiserlich_markers_per_frame' erreicht ist. "
        "Steuerung ausschließlich über den Mindestabstand (min_distance)."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

        # ------------------------------------------------------------------
        # Bootstrap-Parameter laden oder notfalls lokal berechnen
        # ------------------------------------------------------------------
        import math

        params = scene.get("bootstrap_params", None)

        if params:
            # ✅ Normale Initialisierung aus Master-Operator
            md = float(params.get('md', 100))
            ma = int(round(float(params.get('ma', 100)) * 1.1))  # ⚙️ Margin +10% wie gefordert
            tr = float(params.get('tr', 0.5))
            pz = int(params.get('pz', 50))
            sz = int(params.get('sz', 0))
            hz = int(params.get('hz', 1))
            vc = int(params.get('vc', 1))
        else:
            # ⚠️ Fallback-Bootstrap falls kein Master-Bootstrap existiert
            import math

            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                self.report({'ERROR'}, "Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")
                return {'CANCELLED'}

            # --- Basisinformationen aus Clip ---
            hz = clip.size[0]
            vc = clip.size[1]

            scene_obj = getattr(context, "scene", None)
            frame_end = scene_obj.frame_end if scene_obj else None

            # --- Parameter aus Tracking-Settings ---
            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
            pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
            sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100

            # --- Abgeleitete Startwerte ---
            md = hz * 0.025
            tr = 0.0001
            za = ef_target * 4
            og = math.ceil(za * 1.1)
            ug = math.floor(za * 0.9)

            print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
                  f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
                  f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")

        # ----------------------------------------------------------------------
        # BASELINE-FIX:
        # Wir trennen jetzt zwei Konzepte:
        #   (1) pre_snapshot = aktive Marker im Frame → für Cleanup-Vergleich
        #   (2) baseline_start_tracknames = ALLE existierenden Tracks → für finale Selektion
        # ----------------------------------------------------------------------
        pre_snapshot = snapshot_active_markers(context)

        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        baseline_start_tracknames = set()
        if tracking:
            baseline_start_tracknames = {t.name for t in tracking.tracks}

        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | BaselineTracks: {len(baseline_start_tracknames)}")

        # ------------------------------------------------------------------
        # Adaptive Hauptschleife (Snapshot → Detect → Classify → Cleanup → Validate)
        # ------------------------------------------------------------------
        max_loops = 8
        loop = 0
        last_md = md

        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop}/{max_loops} ---")
            print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {last_md:.2f}")

            # 1️⃣ Detect Features
            detect_features(context,
                            placement='FRAME',
                            margin=ma,
                            threshold=tr,
                            min_distance=int(round(last_md)))

            # 2️⃣ Deselect automatisch selektierte Tracks
            clip = context.space_data.clip
            tracking = clip.tracking
            for trk in tracking.tracks:
                trk.select = False

            # 3️⃣ Snapshot & Klassifizierung
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            print(f"[DetectAdapt] Neue Marker erkannt: {len(neue_marker)} (vorher {len(alte_marker)} alte)")

            # 4️⃣ Cleanup vor Bewertung
            cleaned_new, deleted_old = cleanup_new_markers(context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc)
            print(f"[DetectAdapt] Nach Cleanup: {len(cleaned_new)} neue Marker übrig, {deleted_old} alte gelöscht")

            # 5️⃣ Validierung
            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10

            if remaining == 0:
                print("[DetectAdapt] ❌ Keine Marker übrig → min_distance ×0.8")
                last_md = max(2.0, last_md * 0.8)
            elif abs(diff) <= tolerance:
                print(f"[DetectAdapt] ✅ Ziel erreicht: {remaining}/{ef_target} (±{tolerance:.1f})")
                break
            elif remaining < ef_target:
                print(f"[DetectAdapt] Zu wenige Marker ({remaining}/{ef_target}) → min_distance ×0.9")
                last_md = max(2.0, last_md * 0.9)
            else:
                print(f"[DetectAdapt] Zu viele Marker ({remaining}/{ef_target}) → min_distance ×1.1")
                last_md = min(hz * 0.25, last_md * 1.1)

            # 6️⃣ Cleanup temporärer Marker (Vorbereitung auf nächsten Loop)
            delete_tracks_by_names(context, [m['track'] for m in neue_marker])
            print(f"[DetectAdapt] {len(neue_marker)} temporäre Marker gelöscht (Reset).")
            time.sleep(0.1)

        # ------------------------------------------------------------------
        # Endauswertung
        # ------------------------------------------------------------------
        final_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
        for trk in tracking.tracks:
            trk.select = False
        for trk in final_tracks:
            trk.select = True
        print(f"[Kaiserlich Tracker][DetectAdapt] Fertig – {len(final_tracks)} finale Marker.")

        # Selektion der finalen Marker
        clip = getattr(context.space_data, 'clip', None)
        if clip and getattr(clip, 'tracking', None):
            tracking = clip.tracking
            # Nur wirklich neue Tracks selektieren (nicht in globaler Baseline enthalten)
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            try:
                for trk in tracking.tracks:
                    trk.select = False
                for new_trk in new_tracks:
                    new_trk.select = True
                print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")
            except Exception:
                pass

        # Frame-spezifische min_distance speichern & interpolieren
        frame_num = scene.frame_current
        md_value = float(last_md)
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        known_list = list(md_dict.get("known_frames", []))
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = md_value

        if len(known_list) > 1:
            for i in range(len(known_list) - 1):
                f_start = known_list[i]
                f_end = known_list[i + 1]
                if f_end - f_start < 2:
                    continue
                v_start = float(md_dict[str(f_start)])
                v_end = float(md_dict[str(f_end)])
                for f in range(f_start + 1, f_end):
                    t = (f - f_start) / float(f_end - f_start)
                    interp_val = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = interp_val

        print(f"[Kaiserlich Tracker][DetectAdapt] Frame {frame_num}: final min_distance = {md_value:.2f}")
        return {'FINISHED'}
