import bpy
import statistics
import math

def multiscale_temporal_grid_clean(context, area, region, space, tracks, frame_range,
                                   width, height, grid=(6, 6),
                                   start_delta=None, min_delta=3,
                                   outlier_q=0.9, hysteresis_hits=2, min_cell_items=4):
    scene = context.scene
    clip = getattr(space, "clip", None)
    if not clip or not tracks:
        return 0

    # --- start_delta Fallback ---
    if start_delta is None:
        frames_track = getattr(scene, "frames_track", None)
        range_len = int(frame_range[1] - frame_range[0] + 1)
        if frames_track:
            start_delta = max(min_delta * 2, frames_track // 2)
        else:
            start_delta = max(min_delta * 2, range_len // 6)
        start_delta = min(start_delta, max(min_delta * 4, range_len // 2))

    # --- Δ-Pyramide (ASCII) ---
    D0 = int(max(start_delta, min_delta * 2))
    D0 = min(D0, max(24, min_delta * 4))
    deltas = []
    D = D0
    while D >= int(min_delta):
        deltas.append(D)
        D //= 2

    frame_start, frame_end = int(frame_range[0]), int(frame_range[1])

    # --- Helpers (lokal) ---
    pos_cache = {}
    def pos(t, f):
        k = (t.name, f)
        if k in pos_cache:
            return pos_cache[k]
        m = t.markers.find_frame(f)
        if m:
            xy = (m.co[0] * width, m.co[1] * height)
            pos_cache[k] = xy
            return xy
        return None

    gx, gy = grid
    cell_w, cell_h = width / gx, height / gy
    def cell_idx(xy):
        x, y = xy
        cx = min(gx - 1, max(0, int(x // cell_w)))
        cy = min(gy - 1, max(0, int(y // cell_h)))
        return (cx, cy)

    # --- Phase A/B: Coarse→Fine ---
    hits = {}
    valid_tracks = [t for t in tracks if len(t.markers) >= (2 * min_delta + 1)]

    for DD in deltas:
        for f in range(frame_start + DD, frame_end - DD):
            buckets = {}
            for t in valid_tracks:
                p1 = pos(t, f - DD); p0 = pos(t, f); p2 = pos(t, f + DD)
                if not (p1 and p0 and p2):
                    continue
                buckets.setdefault(cell_idx(p0), []).append((t, p1, p2, f))

            for _, items in buckets.items():
                if len(items) < min_cell_items:
                    continue
                flows = [(p2[0] - p1[0], p2[1] - p1[1]) for _, p1, p2, _ in items]
                mx = statistics.median([fx for fx, _ in flows])
                my = statistics.median([fy for _, fy in flows])
                residuals = []
                for t, p1, p2, fcur in items:
                    dx = (p2[0] - p1[0]) - mx
                    dy = (p2[1] - p1[1]) - my
                    r = (dx * dx + dy * dy) ** 0.5
                    residuals.append((t, fcur, r))
                rs = sorted(r for _, _, r in residuals)
                idx = int(max(0, min(len(rs) - 1, len(rs) * float(outlier_q))))
                thr = rs[idx]
                for t, fcur, r in residuals:
                    if r >= thr:
                        key = (t.name, fcur)
                        hits[key] = hits.get(key, 0) + 1

    coarse_delete = {}
    for (tname, f), n in hits.items():
        if n >= int(hysteresis_hits):
            coarse_delete.setdefault(tname, set()).update({f - 1, f, f + 1})

    deleted_coarse = 0
    if coarse_delete:
        tracks_by_name = {t.name: t for t in tracks}
        with context.temp_override(area=area, region=region, space_data=space):
            for tname, frames in coarse_delete.items():
                t = tracks_by_name.get(tname)
                if not t:
                    continue
                for f in sorted(frames):
                    if t.markers.find_frame(f):
                        t.markers.delete_frame(f)
                        deleted_coarse += 1
            try: region.tag_redraw()
            except Exception: pass

    # --- Phase C: Micro-Pass (hypot + MAD) ---
    def _micro_outlier_pass():
        deleted = 0
        with context.temp_override(area=area, region=region, space_data=space):
            for fi in range(frame_start + 1, frame_end - 1):
                buckets = {}
                for tr in tracks:
                    m1 = tr.markers.find_frame(fi - 1)
                    m2 = tr.markers.find_frame(fi)
                    m3 = tr.markers.find_frame(fi + 1)
                    if not (m1 and m2 and m3):
                        continue
                    x = m2.co[0] * width; y = m2.co[1] * height
                    cx = min(gx - 1, max(0, int(x // cell_w)))
                    cy = min(gy - 1, max(0, int(y // cell_h)))
                    vx = (m2.co[0] - m1.co[0]) + (m3.co[0] - m2.co[0])
                    vy = (m2.co[1] - m1.co[1]) + (m3.co[1] - m2.co[1])
                    buckets.setdefault((cx, cy), []).append((tr, fi, vx, vy))

                for _, items in buckets.items():
                    if len(items) < max(3, min_cell_items):
                        continue
                    v_mags = [math.hypot(vx, vy) for _, _, vx, vy in items]
                    med = statistics.median(v_mags)
                    mad = statistics.median([abs(v - med) for v in v_mags]) or 1e-6
                    thr = med + 3.0 * mad
                    for (tr, f, vx, vy), mag in zip(items, v_mags):
                        if mag > thr:
                            for ff in (f - 1, f, f + 1):
                                if tr.markers.find_frame(ff):
                                    tr.markers.delete_frame(ff)
                                    deleted += 1
            try: region.tag_redraw()
            except Exception: pass
        return deleted

    deleted_micro = _micro_outlier_pass()
    return int(deleted_coarse) + int(deleted_micro)
