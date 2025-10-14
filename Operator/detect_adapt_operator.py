import bpy
import time

from ..Helper.bootstrap import run_bootstrap
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

        # ============================================
        # Bootstrap
        # ============================================
        params = run_bootstrap(context, ef_target)
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

        print("\n[Kaiserlich Tracker] ================ Detect Adapt Start ================")
        print(f"[Kaiserlich Tracker] Zielmarker: {ef_target} | Start min_distance={md:.2f}")

        # ============================================
        # Snapshot vor Detect
        # ============================================
        pre_snapshot = snapshot_active_markers(context)
        baseline_start_tracknames = {m['track'] for m in pre_snapshot}

        # ============================================
        # Adaptive Schleife (nur min_distance)
        # ============================================
        max_loops = 8
        loop = 0
        final_new_marker_count = 0
        frame_num = scene.frame_current
        
        # Versuch, gespeicherten Wert zu laden
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])
                print(f"[Kaiserlich Tracker] Verwende gespeicherten min_distance={last_md:.2f} für Frame {frame_num}")
            else:
                # Interpolation falls möglich
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
                        print(f"[Kaiserlich Tracker] Interpolierter Startwert: Frame {f1}={v1:.2f} → Frame {f2}={v2:.2f} → {last_md:.2f}")
                    else:
                        last_md = md
                else:
                    last_md = md
        else:
            last_md = md

        while loop < max_loops:
            loop += 1
            print(f"[Kaiserlich Tracker] Durchlauf {loop} | min_distance={last_md:.2f}")

            # Detect ausführen
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,  # unverändert
                min_distance=int(max(1, round(last_md)))
            )

            # Snapshot nach Detect
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            am = len(neue_marker)
            final_new_marker_count = am

            print(f"[Kaiserlich Tracker] Neue Marker erkannt: {am}")

            # Cleanup
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            remaining = len(cleaned_new)
            print(f"[Kaiserlich Tracker] Cleanup: gelöscht={deleted_old} | verbleibend={remaining}")

            diff = remaining - ef_target
            tolerance = ef_target * 0.10  # 10 % Toleranz
            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker] ✅ Zielanzahl erreicht ({remaining}/{ef_target}) "
                      f"(Toleranz ±{tolerance:.1f})")
                break


            # =======================================================
            # Dynamische Regelung der Mindestdistanz (stabilisiert)
            # =======================================================
            if am > 0:
                ratio = ef_target / am
                new_md = max(0.5, min(2.0, last_md * ratio))
                print(f"[Kaiserlich Tracker] 🔁 Anpassung: md={last_md:.2f} → {new_md:.2f} "
                      f"(Ziel={ef_target}, Neu={am}, Verhältnis={ratio:.3f})")
                last_md = new_md
            else:
                last_md = min(last_md * 1.5, last_md + 50.0)
                print(f"[Kaiserlich Tracker] ⚠️ Keine neuen Marker – Abstand erhöht auf {last_md:.2f}")



            # ⚠️ Nur löschen, wenn weiterer Durchlauf folgt
            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)
            else:
                print("[Kaiserlich Tracker] Letzter Durchlauf – Marker bleiben erhalten.")

        # ============================================
        # Selektion der finalen Marker
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
        # Frame-spezifische min_distance speichern und interpolieren (NEU)
        # ============================================
        frame_num = scene.frame_current
        md_value = float(last_md)
        # Szene-Property initialisieren (falls noch nicht vorhanden)
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        # Bestehende bekannte Frames laden (falls vorhanden)
        if "known_frames" in md_dict:
            known_list = list(md_dict["known_frames"])
        else:
            known_list = []
        # Aktuellen Frame hinzufügen, wenn nicht bereits bekannt
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = md_value
        print(f"[Kaiserlich Tracker] Frame {frame_num}: Endgültiger min_distance={md_value:.2f} gespeichert.")
        # Interpolation durchführen, falls mehr als ein bekannter Frame vorhanden
        if len(known_list) > 1:
            print(f"[Kaiserlich Tracker] Interpoliere min_distance zwischen bekannten Frames...")
            for i in range(len(known_list) - 1):
                f_start = known_list[i]
                f_end = known_list[i + 1]
                if f_end - f_start < 2:
                    continue  # keine Lücke dazwischen
                v_start = float(md_dict[str(f_start)])
                v_end = float(md_dict[str(f_end)])
                # Interpolierte Werte für Zwischen-Frames berechnen
                for f in range(f_start + 1, f_end):
                    t = (f - f_start) / float(f_end - f_start)
                    interp_val = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = interp_val
                print(f"[Kaiserlich Tracker] ... Frame {f_start} (md={v_start:.2f}) bis Frame {f_end} (md={v_end:.2f}): "
                      f"fülle Frames {f_start + 1}–{f_end - 1}.")

        # ============================================
        # Abschlussbericht
        # ============================================
        self.report({'INFO'}, (
            f"Detect abgeschlossen: Neue Marker={final_new_marker_count} | "
            f"Cleanup gelöscht={deleted_old} | Selektiert={selected_new_tracks} | "
            f"Ziel={ef_target} | min_distance={last_md:.2f}"
        ))
        print("[Kaiserlich Tracker] ================ Detect Adapt Ende ==================")
        return {'FINISHED'}
