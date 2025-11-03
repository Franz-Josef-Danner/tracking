# Operator/Master/master_detect_adapt_operator.py
import bpy
import time

from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect import detect_features
from ...Helper.newmarker import classify_markers
from ...Helper.cleaneup import cleanup_new_markers
from ...Helper.delete import delete_tracks_by_names

class KAISERLICHTRACKER_OT_master_detect_adapt(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_detect_adapt"
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



        # Adaptive Schleife
        max_loops = 8
        loop = 0
        final_new_marker_count = 0
        frame_num = scene.frame_current

        # Versuch gespeicherten Wert zu laden
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])
            else:
                if "known_frames" in md_dict and len(md_dict["known_frames"]) >= 2:
                    known = sorted(md_dict["known_frames"])
                    prev_frames = [f for f in known if f < frame_num]
                    next_frames = [f for f in known if f > frame_num]
                    if prev_frames and next_frames:
                        f1 = max(prev_frames)
                        f2 = min(next_frames)
                        v1 = float(md_dict[str(f1)])
                        v2 = float(md_dict[str(f2)])
                        t = (frame_num - f1) / (f2 - f1)
                        last_md = v1 + (v2 - v1) * t
                    else:
                        last_md = md
                else:
                    last_md = md
        else:
            last_md = md

        deleted_old = 0

        while loop < max_loops:
            loop += 1

            # Detect ausführen
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )
            
            # Nach Detect: Blender selektiert automatisch alle neuen Tracks → wir setzen zurück
            clip = getattr(context.space_data, 'clip', None)
            if clip and getattr(clip, 'tracking', None):
                for trk in clip.tracking.tracks:
                    try:
                        trk.select = False
                    except Exception:
                        pass

            # Snapshot nach Detect
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

            if len(neue_marker) > 0:
                print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
            if len(alte_marker) > 0:
                print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])

            # --- Cleanup VOR Bewertung: Entscheidungen basieren auf verbleibenden (gültigen) Neumarkern ---
            am = len(neue_marker)  # reine Info/Transparenz (vor Cleanup)
            final_new_marker_count = am

            # Nach Cleanup (löscht zu nahe Marker, schützt alte)
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            # --- Nach Cleanup: Referenzen und Logging sauber synchronisieren ---
            neue_marker = cleaned_new                      # ab hier ausschließlich bereinigte Neumarker weiterverwenden
            remaining = len(neue_marker)
            final_new_marker_count = remaining

            # Post-Cleanup-Snapshot für Diagnose, ob ALTE Marker versehentlich verschwunden sind
            post_cleanup_snapshot = snapshot_active_markers(context)
            post_cleanup_names = {m['track'] for m in post_cleanup_snapshot}
            deleted_old_names = [m['track'] for m in alte_marker if m['track'] not in post_cleanup_names]
            if deleted_old_names:
                print(f"[⚠️ Kaiserlich Tracker][DetectAdapt] WARNUNG: Alte Marker nach Cleanup verschwunden: {deleted_old_names}")
            
            # --- FIX: Desync nach Cleanup prüfen und korrigieren ---
            if clip and getattr(clip, "tracking", None):
                clip_track_names = {t.name for t in clip.tracking.tracks}
                synced_cleaned = [m for m in neue_marker if m['track'] in clip_track_names]

                if len(synced_cleaned) != len(neue_marker):
                    removed = [m['track'] for m in neue_marker if m['track'] not in clip_track_names]

                else:
                    print("[Fix][DetectAdapt] Kein Desync erkannt – alle Marker existieren noch im Clip.")

                neue_marker = synced_cleaned
                remaining = len(neue_marker)
                final_new_marker_count = remaining
            else:
                print("[Fix][DetectAdapt] Kein aktiver Clip – Sync-Check übersprungen.")

            diff = remaining - ef_target
            tolerance = ef_target * 0.10  # 10 % Toleranz

            if remaining == 0:
                print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Keine gültigen neuen Marker nach Cleanup – weiterer Versuch nötig.")
            elif abs(diff) <= tolerance and remaining > 0:
                break
            else:
                print(f"[Kaiserlich Tracker][DetectAdapt] Abweichung vom Ziel: Δ={diff:+.0f}, Ziel={ef_target}, Toleranz={tolerance:.1f}")

            # --- Neue dynamische md-Anpassung nach Verhältnisformel ---
            if remaining == 0:
                # Sicherheitsfallback, falls alle Marker entfernt
                last_md = max(2.0, last_md * 0.8)
            else:
                ratio = remaining / max(1, ef_target)
                factor = (((ratio - 1.0) / 2.0) + 1.0)
                new_md = last_md * factor
                new_md = min(max(new_md, 2.0), hz * 0.25)
                last_md = new_md

            # Nur löschen, wenn weiterer Durchlauf folgt (bereinigte Neumarker dieses Loops entfernen)
            if loop < max_loops:
                cleaned_names = [m['track'] for m in neue_marker]  # == cleaned_new (bereinigt)
                if cleaned_names:
                    delete_tracks_by_names(context, cleaned_names)
                else:
                    print("[Kaiserlich Tracker][DetectAdapt] Keine bereinigten Neumarker zum Löschen gefunden – übersprungen.")

                time.sleep(0.1)

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

        # ----------------------------------------------------------------------
        # Nach Abschluss: Kontext sicher an master_track_cycle_backwards übergeben
        # ----------------------------------------------------------------------

        try:
            area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
            if area:
                override = context.copy()
                override['area'] = area
                override['region'] = next((r for r in area.regions if r.type == 'WINDOW'), None)

                # ✅ Korrekte Aufrufstruktur: Kontext im temp_override setzen
                with context.temp_override(**override):
                    result = bpy.ops.kaiserlich_tracker.master_track_cycle_backwards(
                        'INVOKE_DEFAULT'
                    )
            else:
                print("[Kaiserlich Tracker][MasterDetectAdapt] ⚠️ Keine CLIP_EDITOR-Area gefunden – Operator-Aufruf übersprungen.")
        except Exception as e:
            print(f"[Kaiserlich Tracker][MasterDetectAdapt] ❌ Fehler beim Start von Track-Cycle-Backwards: {e}")

        return {'FINISHED'}
