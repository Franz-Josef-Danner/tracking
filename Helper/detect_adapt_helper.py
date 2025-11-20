# Helper/detect_adapt_helper.py
# ------------------------------------------------------------
# Kaiserlich Tracker – Adaptive Marker-Detektion (ehem. Operator)
# Führt Detect/Cleanup-Zyklen durch, bis die Zielanzahl erreicht ist.
# Steuerung über dynamischen min_distance.
# ------------------------------------------------------------

import bpy
import time
import math

from .snapshot import snapshot_active_markers
from .detect import detect_features
from .newmarker import classify_markers
from .cleaneup import cleanup_new_markers
from .delete import delete_tracks_by_names


def run_detect_adapt(context: bpy.types.Context) -> None:
    """
    Führt eine adaptive Marker-Detektion durch, bis die Zielanzahl
    aus 'kaiserlich_markers_per_frame' erreicht ist.
    Steuerung ausschließlich über den Mindestabstand (min_distance).
    """
    scene = context.scene
    ef_target = int(scene.kaiserlich_markers_per_frame)

    params = scene.get("bootstrap_params", None)

    if params:
        md = float(params.get("md", 100))
        ma = int(round(float(params.get("ma", 100)) * 1.1))
        tr = float(params.get("tr", 0.5))
        pz = int(params.get("pz", 50))
        sz = int(params.get("sz", 0))
        hz = int(params.get("hz", 1))
        vc = int(params.get("vc", 1))
    else:
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            return

        hz = clip.size[0]
        vc = clip.size[1]
        tracking_settings = getattr(clip.tracking, "settings", None)
        # historischer fallback - wird unten durch default_margin ersetzt
        ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
        pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
        sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100
        md = hz * 0.025
        tr = 0.0001
    # ------------------------------------------------------------------
    # Margin ausschließlich aus MovieTrackingSettings.default_margin
    # → einheitliche Quelle für DeepTest + DetectAdapt + Tracking
    # ------------------------------------------------------------------
    try:
        clip_margin = getattr(context.space_data, "clip", None) if getattr(context, "space_data", None) else None
        if clip_margin is None and getattr(context, "scene", None) is not None:
            clip_margin = getattr(context.scene.tracking, "active", None)

        tracking_settings_margin = (
            getattr(clip_margin.tracking, "settings", None) if clip_margin else None
        )

        if tracking_settings_margin is not None and hasattr(tracking_settings_margin, "default_margin"):
            ma = int(tracking_settings_margin.default_margin)
        else:
            pass
    except Exception as e:
        pass

    pre_snapshot = snapshot_active_markers(context)

    clip = getattr(context.space_data, "clip", None)
    tracking = getattr(clip, "tracking", None) if clip else None
    baseline_start_tracknames = set()
    if tracking:
        baseline_start_tracknames = {t.name for t in tracking.tracks}

    max_loops = 8
    loop = 0
    final_new_marker_count = 0
    frame_num = scene.frame_current

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

        detect_features(
            context,
            placement="FRAME",
            margin=ma,
            threshold=tr,
            min_distance=int(max(1, round(last_md))),
        )

        clip_dbg = getattr(context.space_data, "clip", None)
        if clip_dbg and getattr(clip_dbg, "tracking", None):
            frames = {}
            total_marker_count = 0
            for t in clip_dbg.tracking.tracks:
                for m in t.markers:
                    total_marker_count += 1
                    frames.setdefault(m.frame, 0)
                    frames[m.frame] += 1
            if frames:
                frame_sorted = sorted(frames.items())

        clip = getattr(context.space_data, "clip", None)
        if clip and getattr(clip, "tracking", None):
            for trk in clip.tracking.tracks:
                try:
                    trk.select = False
                except Exception:
                    pass

        post_snapshot = snapshot_active_markers(context)
        alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

        cleaned_new, deleted_old = cleanup_new_markers(
            context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc
        )

        neue_marker = cleaned_new
        remaining = len(neue_marker)
        final_new_marker_count = remaining

        diff = remaining - ef_target
        tolerance = ef_target * 0.10

        if remaining == 0:
            pass
        elif abs(diff) <= tolerance and remaining > 0:
            break

        if remaining == 0:
            last_md = max(2.0, last_md * 0.8)
        else:
            ratio = remaining / max(1, ef_target)
            factor = (((ratio - 1.0) / 2.0) + 1.0)
            new_md = last_md * factor
            new_md = min(max(new_md, 2.0), hz * 0.25)
            last_md = new_md

        if loop < max_loops:
            cleaned_names = [m["track"] for m in neue_marker]
            if cleaned_names:
                delete_tracks_by_names(context, cleaned_names)
            time.sleep(0.1)

    clip = getattr(context.space_data, "clip", None)
    if clip and getattr(clip, "tracking", None):
        tracking = clip.tracking
        new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
        try:
            for trk in tracking.tracks:
                trk.select = False
            for new_trk in new_tracks:
                new_trk.select = True
        except Exception:
            pass

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
