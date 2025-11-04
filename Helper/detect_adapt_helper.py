# Helper/detect_adapt_helper.py
def run_detect_adapt(context: bpy.types.Context) -> None:
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
        ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
        pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
        sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100
        md = hz * 0.025
        tr = 0.0001

    pre_snapshot = snapshot_active_markers(context)
    clip = getattr(context.space_data, "clip", None)
    tracking = getattr(clip, "tracking", None) if clip else None
    baseline_start_tracknames = {t.name for t in tracking.tracks} if tracking else set()

    frame_num = scene.frame_current
    if "min_distance_values" in scene:
        md_dict = scene["min_distance_values"]
        if str(frame_num) in md_dict:
            last_md = float(md_dict[str(frame_num)])
        else:
            last_md = float(md)
    else:
        last_md = float(md)

    max_loops = 8
    loop = 0
    final_new_marker_count = 0

    while loop < max_loops:
        loop += 1
        detect_features(context, placement="FRAME", margin=ma, threshold=tr, min_distance=int(max(1, round(last_md))))

        post_snapshot = snapshot_active_markers(context)
        alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

        cleaned_new, _ = cleanup_new_markers(context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc)
        neue_marker = cleaned_new
        remaining = len(neue_marker)
        final_new_marker_count = remaining

        diff = remaining - ef_target
        tolerance = ef_target * 0.10
        if abs(diff) <= tolerance and remaining > 0:
            break

        ratio = remaining / max(1, ef_target) if remaining > 0 else 0.0
        factor = (((ratio - 1.0) / 2.0) + 1.0)
        last_md = min(max(last_md * factor, 2.0), hz * 0.25)

        if loop < max_loops and neue_marker:
            delete_tracks_by_names(context, [m["track"] for m in neue_marker])
            time.sleep(0.1)

    clip = getattr(context.space_data, "clip", None)
    if clip and getattr(clip, "tracking", None):
        tracking = clip.tracking
        new_tracks = [t for t in tracking.tracks if t.name not in baseline_start_tracknames]
        try:
            for t in tracking.tracks:
                t.select = False
            for t in new_tracks:
                t.select = True
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
                md_dict[str(f)] = v_start + (v_end - v_start) * t

    print(f"[DetectAdapt] ✅ Abgeschlossen – Marker={final_new_marker_count}, min_distance={last_md:.2f}")
