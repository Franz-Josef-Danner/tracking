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

            # Snapshot nach Detect
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            am = len(neue_marker)
            final_new_marker_count = am

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
            diff = remaining - ef_target
            tolerance = ef_target * 0.10  # 10 % Toleranz
            if abs(diff) <= tolerance:
                break

            # Dynamische Anpassung des Mindestabstands
            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                new_md = last_md / factor
                last_md = max(1.0, new_md)
            else:
                # Sicherheitsfallback bei 0 neuen Markern
                last_md = last_md * 1.5

            # Nur löschen, wenn weiterer Durchlauf folgt
            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)

        # ============================================
        # Selektion der finalen Marker
        # ============================================
        clip = getattr(context.space_data, 'clip', None)
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
            except Exception:
                pass

        # ============================================
        # Frame-spezifische min_distance speichern & interpolieren
        # ============================================
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

        # ============================================
        # Abschlussmeldung an Blender
        # ============================================
        self.report({'INFO'}, (
            f"Detect abgeschlossen: Neue Marker={final_new_marker_count} | "
            f"Cleanup gelöscht={deleted_old} | Selektiert={selected_new_tracks} | "
            f"Ziel={ef_target} | min_distance={last_md:.2f}"
        ))
        return {'FINISHED'}
